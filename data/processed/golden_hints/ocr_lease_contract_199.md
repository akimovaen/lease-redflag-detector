# Hints for ocr_lease_contract_199

Text: `data/texts/ocr_lease_contract_199.txt` (2996 words, dirt: broken_layout;ocr). Golden file: `data/golden/ocr_lease_contract_199.json`.

Spans annotated by the ALeaseBERT authors. Values must be normalized to the schema (ISO dates, numbers, enums); quotes must be copied from the text file, not from here.

Red flag definitions:

- landlord_repairs: the landlord bears repairs or maintenance beyond the structure of the building, e.g. building systems, facilities or normal wear and tear.
- service_charges_limited: the landlord bears operating costs (management fees, utilities, taxes, insurance), they are included in the rent, or the tenant's share is capped or may be refused.
- tenant_break_option: the tenant may terminate before the end date on its own decision, with or without notice or a penalty. Not the landlord's right to terminate for the tenant's breach, and not a termination that needs the landlord's consent.
- indexation_limited: the rent cannot be increased, increases are capped, or they require the tenant's agreement.
- sublease_permitted: the tenant may sublet or assign without the landlord's consent, the landlord may not refuse or unreasonably withhold consent, or certain subtenants are pre-approved.

## ALeaseBERT entities

### lessor

- ~line 27 (OCR text differs): Lessor: Korea Institute of Design Promotion (hereinafter named as “Lessor”)
- ~line 39 (OCR text differs): Lessor: KIDP Lesee: Leadis Technology Korea, Inc.
- ~line 41 (OCR text differs): Address: 344-1, Yatap 1-dong Address: Korea Design Center, Room
- ~line 43 (OCR text differs): Bundang-gu, Seongnam 205, 344-1, Yatap 1-dong, Bundang-gu,
- ~line 45 (OCR text differs): Kyunggi-do Seongnam, Kyunggi-do
- ~line 47 (OCR text differs): Representative: Kim, Chul Ho Representative: Ahn, Sung Tae
- ~line 27 (OCR text differs): Lessor, Korea Institute of Design Promotion (hereinafter named as ‘A’)
- ~line 39 (OCR text differs): Lessor: KIDP

### lessee

- ~line 29 (OCR text differs): Lessee: Leadis Technology Korea, Inc. (hereinafter named as “Lessee”)
- ~line 29 (OCR text differs): Lessee, Leadis Technology Korea, Inc. (hereinafter named as ‘B’)
- ~line 29 (OCR text differs): Lessee: Leadis Technology Korea, Inc.
- ~line 41 (OCR text differs): Address: 344-1, Yatap 1-dong
- ~line 365 (OCR text differs): 344-Bundang-gu, Seongnam
- ~line 45 (OCR text differs): Kyunggi-do
- ~line 367 (OCR text differs): Room 205 Korea Design Center, Room 1
- ~line 368 (OCR text differs): Yatap 1-dong, Bundang- gu,
- ~line 369 (OCR text differs): Seongnam, Kyunggi-do
- ~line 47 (OCR text differs): Representative: Kim, Chul Ho
- ~line 371 (OCR text differs): Representative: Ahn, Sung Tae

### premises_address, area (leased_space)

- ~line 43 (OCR text differs): Room 802, 8th floor, Korea Design Center, 344-1, Yatap 1–dong, Bundang–gu, Seongnam, Kyunggi–do (size–105.10 pyung(347.44 sqm))

### start_date

- ~line 19 (OCR text differs): March 25, 2004

### end_date

- ~line 37 (OCR text differs): March 24, 2006

### rent (term_of_payment)

- ~line 66 (OCR text differs): Monthly Rent: Won four million and two hundred and four thousand ((Won)4,204,000) without VAT
- ~line 126 (OCR text differs): The term for assessing monthly rent and management expenses shall be from the first to the last day of each month. “B” shall pay “A” the amount stipulated in Clause 5 and 6 of Article 2 by the due date stipulated in Clause 7.
- ~line 129 (OCR text differs): In case that the commencement or termination of lease term falls on the middle of month, the rent and management expenses shall be calculated in accordance with the number of days.

### indexation (indexation_rent)

- ~line 146 (OCR text differs): Even during the lease term, “A” is entitled to adjust guaranty money, rent and management expenses through negotiation with “B” by written notification of 30 days in advance in the following cases.
- ~line 149 (OCR text differs): A.increment of tax and public charges
- ~line 151 (OCR text differs): B.price increase or extreme economic fluctuation
- ~line 153 (OCR text differs): C.increment of expense for air-conditioning and heating, labor and other maintenance/management expenses of the building

## ALeaseBERT red flags

Check each one: is it risky for the landlord under the definitions above?

- [guarantee_transferable] ~line 64 (OCR text differs): Guaranty Money the lease: Won eighty four million and eighty thousand ((Won)84,080,000)
- [services_charges] ~line 68 (OCR text differs): Monthly Management Expenses: Won one million and eight hundred and ninety one thousand and eight hundred ((Won)1,891,800) without VAT
- [services_charges] ~line 72 (OCR text differs): Due Date of Management Expenses: fifteenth day of the month
- [break_option] ~line 84 (OCR text differs): If ‘B’ wishes to cancel the contract during the lease term, ‘B’ shall notify ‘A’ in writing 60 days in advance without fail. In this case, this contract is terminated on the 60th day from the day when ‘A’ receives the written notification.
- [break_option] ~line 88 (OCR text differs): If ‘B’ wishes to cancel the contract 60 days in advance in accordance with Clause 3 of Article 4, ‘B’ shall pay ‘A’ amount calculated at the annual interest rate of 15% against the guaranty money for the term ranging from the next day of contract cancellation to the 60th day, rent and management expenses. However, the term for imposing penalty shall be until either the 60th day from the day when ‘A’ receives written notification of contract cancellation or expiry date of lease contract, whichever comes earlier.
- [reinstatement_clause] ~line 122 (OCR text differs): Within 14 days after “B” completes restoring state of object matter of the lease, “A” shall return guaranty money. For delayed return of guaranty money, delay charge at the annual interest rate of 15% shall be imposed to “A”.
- [services_charges] ~line 132 (OCR text differs): The management expenses stipulated in Clause 6 of Article 2 include expense for air-conditioning, heating, cleaning, electricity, water supply and so forth.
- [change_of_control] ~line 159 (OCR text differs): “B” shall not transfer or provide as mortgage the right of lease nor sublet the object matter of lease to the 3rd party.
- [sublease_permitted] ~line 161 (OCR text differs): Without the written consent of “A”, “B” shall not let other persons use the object matter of lease nor put up a notice of name of persons in the room nor use it as liaison office.
- [break_option] ~line 199 (OCR text differs): In case that “B” commits any of the following behaviors, “A” is entitled to cancel this contract without prior notification, retrieve the object matter and take necessary legal actions.
- [break_option] ~line 204 (OCR text differs): A.Nonpayment of rent or other charges for more than 2 months
- [break_option] ~line 206 (OCR text differs): B.In case that the right to claim the restitution of guaranty money is subject to the right of pledge or other mortgage or compulsory execution
- [break_option] ~line 209 (OCR text differs): C.In case that “B” is in bankruptcy or insolvency; in case that transference of the property or composition is in effect with his creditor to settle liabilities and application for the liquidation of company owned by “B” is made
- [break_option] ~line 212 (OCR text differs): D.Breach of any provisions in this contract
- [reinstatement_clause] ~line 264 (OCR text differs): In case that this contract is terminated, “B” shall move out his belongings and property before the terminating date, return keys and property of “A” to “A” and vacate all object matter of the lease.
- [reinstatement_clause] ~line 269 (OCR text differs): “B” shall move out the equipment, partition and other structural facilities installed by him at his cost to ensure restoration to the original state as that of the time when this contract was concluded.
- [reinstatement_clause] ~line 274 (OCR text differs): If “B” evacuates without moving out his belongings or property or restoring the object matter to its original state, “B” shall pay “A” penalty which is in double of the normal rent for the period from the expiry date of this contract to the date when evacuation or restoration is actually completed. Normal rent is the sum of amount calculated by applying annual interest rate of 16% to guaranty money, rent and management expenses.
- [landlord_repairs] ~line 290 (OCR text differs): “A” shall bear the repair expense for the naturally worn or discolored wall, ceiling, floor, etc, of the object matter of the lease. “B” shall bear the other repair expense.
