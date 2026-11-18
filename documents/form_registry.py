# SPDX-License-Identifier: MPL-2.0
"""Research inventory for demo review, not an applicability or form-generation engine.

Registry revisions describe this code's research inventory, not official form
revisions. Nothing here authorizes production use or declares a form required.
"""
from dataclasses import dataclass

REGISTRY_VERSION = 'fl-research-2026-11-18-v7'


@dataclass(frozen=True)
class DocumentReference:
    key: str
    name: str
    workflows: tuple[str, ...]
    publisher: str
    revision: str
    rights: str
    applicability: str
    review: str
    source: str
    facts: tuple[str, ...] = ()


REFERENCES = (
    DocumentReference(
        'title', 'Florida motor vehicle title application (HSMV 82040 MV)',
        ('cash', 'bhph', 'other'), 'FLHSMV',
        'HSMV 82040 MV rev. 07/23. FLHSMV PDF directly downloaded and extracted 2026-11-18.',
        'Official FLHSMV form; reproduction, redistribution, electronic completion and filing acceptance unverified.',
        'Review vehicle, transaction, jurisdiction and correct title procedure; no automatic determination.',
        'Review applicant/co-owner, vehicle, ownership, liens, odometer, brand, signatures and supporting evidence; unknowns remain unknown.',
        'https://www.flhsmv.gov/pdf/forms/82040.pdf', ('buyer', 'address', 'vin', 'brand'),
    ),
    DocumentReference(
        'buyers-guide', 'FTC Buyers Guide', ('cash', 'bhph', 'other'), 'FTC',
        'FTC fillable form page dated November 2016; amended rule effective January 28, 2017. Verify current form before use.',
        'FTC permits downloading or computer generation subject to rule format; other reproduction and redistribution rights require review.',
        'Review dealer and vehicle definitions, exemptions, sale circumstances and jurisdiction; no automatic determination.',
        'Review prominent display, final copy at sale, Spanish-language sales, warranty choices and contract consistency.',
        'https://www.ftc.gov/business-guidance/resources/dealers-guide-used-car-rule', ('vin',),
    ),
    DocumentReference('sale-agreement', 'Sale agreement / buyer’s order', ('cash', 'bhph', 'other'), 'Not selected', 'Not selected', 'Template rights not established', 'Review appropriate contract and supporting documents for the transaction.', 'Obtain reviewed template; verify terms, signatures, copies and retention.', 'https://www.flhsmv.gov/pdf/dealerservices/dealerhandbook.pdf', ('buyer',)),
    DocumentReference('brand', 'Vehicle brand disclosure', ('cash', 'bhph', 'other'), 'Not selected', 'Not selected', 'Template rights not established', 'Review recorded brand and applicable disclosure requirements; do not infer from this list.', 'Verify disclosure wording, timing and delivery for the facts.', 'https://www.leg.state.fl.us/Statutes/index.cfm?App_mode=Display_Statute&StatuteYear=2026&URL=0300-0399/0319/Sections/0319.14.html', ('brand',)),
    DocumentReference(
        'odometer', 'Odometer disclosure / title reassignment', ('cash', 'bhph', 'other'), 'NHTSA / FLHSMV',
        '49 CFR Part 580 reviewed 2026-11-10; HSMV 82993 rev. 11/11. FLHSMV PDF directly downloaded and extracted 2026-11-18.',
        'Florida form reproduction, electronic acceptance and form use require verification.',
        'Review title, transfer, vehicle and exemptions; no automatic determination. A separate form is not always appropriate.',
        'Review VIN, vehicle identity, transfer date, mileage/status, parties, addresses and signatures; verify title or authorized reassignment.',
        'https://www.ecfr.gov/current/title-49/subtitle-B/chapter-V/part-580', ('vin', 'odometer'),
    ),
    DocumentReference(
        'dealer-reassignment', 'Dealer title reassignment supplement (HSMV 82994)',
        ('cash', 'bhph', 'other'), 'FLHSMV',
        'HSMV 82994 rev. 04/14. Procedure TL-09 rev. 06/2026, effective immediately. Both FLHSMV PDFs directly downloaded and extracted 2026-11-18.',
        'TL-09 identifies secure stock; procurement, reproduction and electronic acceptance unverified.',
        'Review title type, assignment chain, available spaces and transaction; no automatic determination.',
        'Review VIN, title and vehicle identity, dealer/seller and purchaser details, mileage, dates, signatures and sequence.',
        'https://www.flhsmv.gov/pdf/proc/tl/tl-09.pdf', ('vin', 'odometer'),
    ),
    DocumentReference(
        'secure-odometer-poa', 'Secure odometer power of attorney (HSMV 82995)',
        ('cash', 'bhph', 'other'), 'FLHSMV / NHTSA',
        'Procedure TL-02 rev. 03/25, effective immediately. FLHSMV procedure PDF directly downloaded and extracted 2026-11-18. Secure HSMV 82995 form revision remains unverified.',
        'Jurisdiction-issued secure form; procurement, reproduction and electronic acceptance unverified.',
        'Review title availability, parties and authority, jurisdiction and exemptions; no automatic determination.',
        'Review VIN, parties, named agent, mileage/status, signatures, title sequence, Part C certification and original submission.',
        'https://www.flhsmv.gov/pdf/proc/tl/tl-02.pdf', ('vin', 'odometer'),
    ),
    DocumentReference(
        'retail-installment', 'Retail installment contract and credit disclosures',
        ('bhph', 'other'), 'CFPB / Florida Legislature; contract template not selected',
        'CFPB current regulation and 2026 Florida compilation reviewed 2026-11-10; transaction-specific effective dates remain unverified.',
        'No contract template selected; template rights and reproduction remain unverified.',
        'Review creditor, consumer purpose, exemptions, credit/sale terms and Florida contract scope; no automatic determination.',
        'Review APR as annual credit cost rate, amount financed as net credit, finance charge as dollar credit cost, and total of payments as scheduled payments; also review schedule, itemization, timing, signing and delivery with counsel and finance specialists.',
        'https://www.consumerfinance.gov/rules-policy/regulations/1026/18/', ('buyer', 'financing'),
    ),
    DocumentReference('trade', 'Trade-in title and lien documents', ('cash', 'bhph', 'other'), 'Depends on transaction', 'Not selected', 'Verify the source and rights for each document', 'Review only when a trade is involved and verify title, lien and mileage requirements.', 'Identify correct documents, ownership, lien payoff and any secure forms.', 'https://www.flhsmv.gov/pdf/dealerservices/dealerhandbook.pdf'),
)


def research_inventory(snapshot):
    """Use saved facts only; an unknown deal type must not exclude finance topics."""
    deal_type = snapshot.get('deal_type')
    workflow = {'Cash': 'cash', 'Buy here, pay here': 'bhph'}.get(deal_type, 'other')
    buyer = snapshot.get('buyer') or {}
    vehicle = snapshot.get('vehicle') or {}
    facts = vehicle.get('facts') or {}
    missing = {
        'buyer': not bool(buyer.get('name')),
        'address': not bool(buyer.get('address_lines')),
        'vin': facts.get('VIN') in (None, '', 'Not recorded'),
        'brand': facts.get('Title brand as recorded') in (None, '', 'Not recorded', 'Not verified'),
        'odometer': facts.get('Odometer reading') in (None, '', 'Not recorded'),
        'financing': not bool(snapshot.get('proposal')),
    }
    labels = {'buyer': 'Buyer name', 'address': 'Buyer address', 'vin': 'VIN', 'brand': 'Title brand verification', 'odometer': 'Odometer reading', 'financing': 'Financing proposal'}
    entries = []
    for reference in REFERENCES:
        if workflow not in reference.workflows:
            continue
        if reference.key == 'trade' and not snapshot.get('trade'):
            continue
        entries.append({'reference': reference, 'missing': [labels[key] for key in reference.facts if missing[key]]})
    return entries
