# SPDX-License-Identifier: MPL-2.0
def draft_totals(amounts):
    """Decimal worksheet arithmetic only; this does not calculate credit terms."""
    fees = amounts["tax"] + amounts["title_registration"] + amounts["dealer_fee"]
    return {
        "price": amounts["sale_price"],
        "fees": fees,
        "trade_allowance": amounts["trade_allowance"],
        "trade_payoff": amounts["trade_payoff"],
        "trade_adjustment": amounts["trade_payoff"] - amounts["trade_allowance"],
        "down_payment": amounts["down_payment"],
        "balance": amounts["sale_price"] + fees + amounts["trade_payoff"] - amounts["trade_allowance"] - amounts["down_payment"],
    }
