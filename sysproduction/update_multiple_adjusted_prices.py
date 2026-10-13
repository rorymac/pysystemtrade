"""
Update multiple and adjusted prices

We do this together, to ensure consistency

Two types of services:
- bulk, run after end of day data
- listener, run constantly as data is sampled
- the

"""

import numpy as np

from syscore.constants import success
from syscore.exceptions import missingData

from sysobjects.dict_of_named_futures_per_contract_prices import (
    contract_name_from_column_name,
    dictNamedFuturesContractFinalPrices,
    dictFuturesNamedContractFinalPricesWithContractID,
    forward_name,
    price_name,
)

from sysobjects.adjusted_prices import (
    no_update_roll_has_occurred,
    futuresAdjustedPrices,
)
from sysobjects.multiple_prices import (
    futuresMultiplePrices,
    setOfNamedContracts,
    singleRowMultiplePrices,
)
from sysobjects.contracts import futuresContract

from sysdata.data_blob import dataBlob
from sysproduction.data.contracts import dataContracts
from sysproduction.data.prices import (
    diagPrices,
    updatePrices,
    get_valid_instrument_code_from_user,
)

ALL_INSTRUMENTS = "ALL"


def update_multiple_adjusted_prices():
    """
    Do a daily update for multiple and adjusted prices

    :return: Nothing
    """

    with dataBlob(log_name="Update-Multiple-Adjusted-Prices") as data:
        update_multiple_adjusted_prices_object = updateMultipleAdjustedPrices(data)

        instrument_code = get_valid_instrument_code_from_user(
            all_code=ALL_INSTRUMENTS, allow_all=True
        )

        update_multiple_adjusted_prices_object.update_multiple_adjusted_prices(
            instrument_code=instrument_code
        )
        if instrument_code is ALL_INSTRUMENTS:
            ## done
            return success

        ## else go into a loop
        do_another = True

        while do_another:
            EXIT_CODE = "EXIT"
            instrument_code = get_valid_instrument_code_from_user(
                allow_exit=True, exit_code="EXIT"
            )
            if instrument_code is EXIT_CODE:
                do_another = False
            else:
                update_multiple_adjusted_prices_object.update_multiple_adjusted_prices(
                    instrument_code=instrument_code
                )

    return success


class updateMultipleAdjustedPrices(object):
    def __init__(self, data: dataBlob):
        self.data = data

    def update_multiple_adjusted_prices(self, instrument_code: str = ALL_INSTRUMENTS):
        data = self.data
        update_multiple_adjusted_prices_with_data(data, instrument_code=instrument_code)


def update_multiple_adjusted_prices_with_data(
    data: dataBlob, instrument_code: str = ALL_INSTRUMENTS
):
    diag_prices = diagPrices(data)
    if instrument_code == ALL_INSTRUMENTS:
        list_of_codes = diag_prices.get_list_of_instruments_in_multiple_prices()
    else:
        list_of_codes = [instrument_code]

    for instrument_code in list_of_codes:
        try:
            update_multiple_adjusted_prices_for_instrument(instrument_code, data)
        except Exception as e:
            data.log.critical(
                "Something went wrong with adjusted prices for %s! [%s]"
                % (instrument_code, str(e))
            )


def update_multiple_adjusted_prices_for_instrument(
    instrument_code: str, data: dataBlob
):
    """
    Update for multiple and adjusted prices for a given instrument

    :param instrument_code:
    :param data: dataBlob
    :param log: logger
    :return: None
    """

    data.log.debug(
        "Updating log attributes",
        method="clear",
        instrument_code=instrument_code,
    )
    updated_multiple_prices = calc_updated_multiple_prices(data, instrument_code)
    updated_adjusted_prices = calc_update_adjusted_prices(
        data, instrument_code, updated_multiple_prices
    )

    update_with_new_prices(
        data,
        instrument_code,
        updated_adjusted_prices=updated_adjusted_prices,
        updated_multiple_prices=updated_multiple_prices,
    )


def calc_updated_multiple_prices(
    data: dataBlob, instrument_code: str
) -> futuresMultiplePrices:
    diag_prices = diagPrices(data)
    # update multiple prices with new prices
    # (method in multiple prices object and possible in data socket)
    existing_multiple_prices = diag_prices.get_multiple_prices(instrument_code)

    relevant_contracts = existing_multiple_prices.current_contract_dict()
    existing_multiple_prices = switch_expired_carry_contract(
        data, instrument_code, existing_multiple_prices, relevant_contracts
    )
    relevant_contracts = existing_multiple_prices.current_contract_dict()

    new_prices_dict = get_dict_of_new_prices_and_contractid(
        instrument_code, relevant_contracts, data
    )
    updated_multiple_prices = existing_multiple_prices.update_multiple_prices_with_dict(
        new_prices_dict
    )

    return updated_multiple_prices


def calc_update_adjusted_prices(
    data: dataBlob, instrument_code: str, updated_multiple_prices: futuresMultiplePrices
) -> futuresAdjustedPrices:
    diag_prices = diagPrices(data)
    existing_adjusted_prices = diag_prices.get_adjusted_prices(instrument_code)

    updated_adjusted_prices = (
        existing_adjusted_prices.update_with_multiple_prices_no_roll(
            updated_multiple_prices
        )
    )

    if updated_adjusted_prices is no_update_roll_has_occurred:
        msg = (
            "Can't update adjusted prices for %s as roll has occurred but not registered properly"
            % instrument_code
        )
        data.log.critical(msg)
        raise Exception(msg)

    return updated_adjusted_prices


def switch_expired_carry_contract(
    data: dataBlob,
    instrument_code: str,
    existing_multiple_prices: futuresMultiplePrices,
    relevant_contracts: setOfNamedContracts,
) -> futuresMultiplePrices:
    """
    Point carry at the next priced contract once the nearer one has expired.

    This is not a price roll: PRICE and FORWARD stay where they are. Adjusted
    prices only stitch when PRICE_CONTRACT changes.
    """
    diag_contracts = dataContracts(data)
    replacement_id = diag_contracts.replacement_for_expired_carry_contract(
        instrument_code,
        carry_contract_id=str(relevant_contracts.carry),
        priced_contract_id=str(relevant_contracts.price),
    )
    if replacement_id is None:
        return existing_multiple_prices

    return _append_carry_switch_row(
        data, instrument_code, existing_multiple_prices, replacement_id
    )


def _append_carry_switch_row(
    data: dataBlob,
    instrument_code: str,
    multiple_prices: futuresMultiplePrices,
    new_carry_contract_id: str,
) -> futuresMultiplePrices:
    last = multiple_prices.iloc[-1]
    carry_price = _latest_final_price(data, instrument_code, new_carry_contract_id)
    switched_row = singleRowMultiplePrices(
        price=_float_or_nan(last[price_name]),
        forward=_float_or_nan(last[forward_name]),
        carry=carry_price,
        price_contract=str(last[contract_name_from_column_name(price_name)]),
        forward_contract=str(last[contract_name_from_column_name(forward_name)]),
        carry_contract=str(new_carry_contract_id),
    )
    return switched_row.concat_with_multiple_prices(multiple_prices)


def _latest_final_price(
    data: dataBlob, instrument_code: str, contract_id: str
) -> float:
    diag_prices = diagPrices(data)
    contract = futuresContract(instrument_code, contract_id)
    try:
        prices = diag_prices.get_merged_prices_for_contract_object(
            contract
        ).return_final_prices()
    except missingData:
        return np.nan
    prices = prices.dropna()
    if len(prices) == 0:
        return np.nan
    return float(prices.iloc[-1])


def _float_or_nan(value) -> float:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return np.nan
    try:
        if np.isnan(value):
            return np.nan
    except TypeError:
        return np.nan
    return float(value)


def get_dict_of_new_prices_and_contractid(
    instrument_code: str, contract_date_dict: setOfNamedContracts, data: dataBlob
) -> dictFuturesNamedContractFinalPricesWithContractID:
    """

    :param instrument_code: str
    :param contract_list: dict of 'yyyymmdd' str, keynames 'CARRY, PRICE, FORWARD'
    :param data:
    :return: dict of futures contract prices for each contract, plus contract id column
    """
    diag_prices = diagPrices(data)
    # get prices for relevant contracts, return as dict labelled with column
    # for contractids
    relevant_contract_prices = dict()
    for key, contract_date_str in contract_date_dict.items():
        contract = futuresContract(instrument_code, contract_date_str)
        price_series = diag_prices.get_merged_prices_for_contract_object(contract)
        relevant_contract_prices[key] = price_series.return_final_prices()

    relevant_contract_prices = dictNamedFuturesContractFinalPrices(
        relevant_contract_prices
    )

    new_prices_dict = (
        dictFuturesNamedContractFinalPricesWithContractID.create_from_two_dicts(
            relevant_contract_prices, contract_date_dict
        )
    )

    return new_prices_dict


def update_with_new_prices(
    data,
    instrument_code: str,
    updated_multiple_prices: futuresMultiplePrices,
    updated_adjusted_prices: futuresAdjustedPrices,
):
    update_prices = updatePrices(data)

    update_prices.add_multiple_prices(
        instrument_code, updated_multiple_prices, ignore_duplication=True
    )
    update_prices.add_adjusted_prices(
        instrument_code, updated_adjusted_prices, ignore_duplication=True
    )


if __name__ == "__main__":
    update_multiple_adjusted_prices()
