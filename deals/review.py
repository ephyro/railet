# SPDX-License-Identifier: MPL-2.0
"""Presentation helpers for the read-only draft deal review."""


def has_value(value):
    """Treat zero as a recorded value while keeping null and blank unknown."""
    return value is not None and not (isinstance(value, str) and not value.strip())


def money_text(value):
    """Format an existing Decimal amount without converting through float."""
    if value is None:
        return "Not recorded"
    amount = format(abs(value), ",.2f")
    return f"-${amount}" if value < 0 else f"${amount}"


def build_review_reminders(deal, trade, proposal, links):
    """List blank or unverified facts for a person to review, not legal checks."""
    reminders = []

    def add(title, detail, link_key, action):
        reminders.append({
            "title": title,
            "detail": detail,
            "url": links[link_key],
            "action": action,
        })

    vehicle = deal.vehicle
    if not has_value(vehicle.vin):
        add("Vehicle VIN is not recorded.", "Compare the vehicle record with its source documents.", "vehicle", "Review vehicle")
    if vehicle.title_brand == "unknown":
        add("Vehicle title brand is not verified.", "Check the title evidence and any applicable disclosure with a reviewer.", "vehicle", "Review vehicle")
    if not vehicle.title_received:
        add("Vehicle title is not marked as received.", "Follow up on the title evidence for this vehicle.", "vehicle", "Review vehicle")
    if (
        vehicle.odometer_reading is None
        or vehicle.odometer_unit == "unknown"
        or vehicle.odometer_status == "unknown"
    ):
        add("Vehicle mileage details are incomplete or not verified.", "Keep the reading and reported status as recorded; compare them with source evidence.", "vehicle", "Review vehicle")

    if not has_value(deal.buyer.phone) and not has_value(deal.buyer.email):
        add("No phone or email is recorded for the buyer.", "Add contact details if they are available.", "buyer", "Review buyer")
    if deal.co_buyer and not has_value(deal.co_buyer.phone) and not has_value(deal.co_buyer.email):
        add("No phone or email is recorded for the co-buyer.", "Add contact details if they are available.", "co_buyer", "Review co-buyer")

    if deal.deal_type == "undecided":
        add("Deal type has not been selected.", "Review the saved draft before continuing.", "deal", "Review deal")

    if trade:
        identity_recorded = has_value(trade.vin) or (
            has_value(trade.year) and has_value(trade.make) and has_value(trade.model)
        )
        if not identity_recorded:
            add("Trade-in identity is incomplete.", "Compare the recorded details with the trade vehicle documents.", "trade", "Review trade-in")
        if trade.title_brand == "unknown":
            add("Trade-in title brand is not verified.", "Check the title evidence with a reviewer.", "trade", "Review trade-in")
        if (
            trade.odometer_reading is None
            or trade.odometer_unit == "unknown"
            or trade.odometer_status == "unknown"
        ):
            add("Trade-in mileage details are incomplete or not verified.", "Keep the reading and reported status as recorded; compare them with source evidence.", "trade", "Review trade-in")
        if deal.trade_payoff > 0 and not has_value(trade.lienholder_name):
            add("An estimated trade payoff is entered, but no lienholder or recipient is recorded.", "Confirm the recipient for this estimate.", "trade", "Review trade-in")
        if deal.trade_payoff > 0 and trade.payoff_good_through is None:
            add("No date is recorded for the estimated trade payoff.", "Check whether the estimate is current.", "trade", "Review trade-in")
    elif deal.trade_allowance != 0 or deal.trade_payoff != 0:
        add("Trade amounts are in the worksheet, but no active trade-in record is saved.", "Compare the worksheet amounts with the intended trade details.", "trade", "Review trade-in")

    if proposal:
        fields = (
            ("creditor_name", "Creditor or funding source"),
            ("payment_frequency", "Payment frequency"),
            ("payment_count", "Payment count"),
            ("annual_contract_rate", "Annual contract rate entered (not APR)"),
            ("first_payment_date", "First payment date"),
        )
        missing = [label for name, label in fields if not has_value(getattr(proposal, name))]
        if missing:
            add(
                "Some saved financing proposal fields are blank.",
                "Review which details apply and add any missing proposal facts: " + ", ".join(missing) + ".",
                "proposal",
                "Review deal",
            )
    elif deal.deal_type in ("outside", "bhph"):
        add("No proposal is saved for the selected financing type.", "Review the deal worksheet and its proposed terms.", "proposal", "Review deal")

    return reminders
