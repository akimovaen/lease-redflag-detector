# Hints for ocr_lease_contract_11

Text: `data/texts/ocr_lease_contract_11.txt` (1950 words, dirt: broken_layout;ocr). Golden file: `data/golden/ocr_lease_contract_11.json`.

Spans annotated by the ALeaseBERT authors. Values must be normalized to the schema (ISO dates, numbers, enums); quotes must be copied from the text file, not from here.

Red flag definitions:

- landlord_repairs: the landlord bears repairs or maintenance beyond the structure of the building, e.g. building systems, facilities or normal wear and tear.
- service_charges_limited: the landlord bears operating costs (management fees, utilities, taxes, insurance), they are included in the rent, or the tenant's share is capped or may be refused.
- tenant_break_option: the tenant may terminate before the end date on its own decision, with or without notice or a penalty. Not the landlord's right to terminate for the tenant's breach, and not a termination that needs the landlord's consent.
- indexation_limited: the rent cannot be increased, increases are capped, or they require the tenant's agreement.
- sublease_permitted: the tenant may sublet or assign without the landlord's consent, the landlord may not refuse or unreasonably withhold consent, or certain subtenants are pre-approved.

## ALeaseBERT entities

### lessor

- ~line 9 (OCR text differs): (Party A): Shanghai New Cogi Cosmetic Co., Ltd.

### lessee

- ~line 11 (OCR text differs): (Party B): Shanghai Mecox Lane Information Technology Co., Ltd.

### premises_address, area (leased_space)

- ~line 18 (OCR text differs): premises located at the west part of 17th Floor, Diamond Building, 487 Tianlin Road, Xuhui District, Shanghai (hereinafter the “Premises”). The construction area of the Premises is 967.38 square meters.

### start_date

- ~line 178 (OCR text differs): August 20, 2009

### end_date

- ~line 178 (OCR text differs): August 19, 2012

### rent (term_of_payment)

- ~line 46 (OCR text differs): Rental-free period shall commence on August 20, 2009 and expire on October 8, 2009. During the rental-free period, Party B shall bear the property management fees.
- ~line 54 (OCR text differs): Both parties agree that the monthly rent of the Premises is RMB85,330. (In capital: RMB EIGHTY FIVE THOUSAND AND THREE HUNDRED AND THIRTY.) The rent shall remain unchanged during the tenancy.
- ~line 57 (OCR text differs): Party B shall pay the rent after the receipt of the invoice issued by Party A. If Party B fails to pay punctually, for every single day of delay, it shall pay a penalty to Party A at the rate of 0.3% of the monthly rent.
- ~line 60 (OCR text differs): The method of payment of the rent shall be as follows: To be pre-paid quarterly. On execution of this Contract, Party B shall pay Party A the earnest money equal to three times of the monthly rent in the amount of RMB255,990, which shall automatically be converted to rent on expiration of the rental-free period.

## ALeaseBERT red flags

Check each one: is it risky for the landlord under the definitions above?

- [guarantee_transferable] ~line 69 (OCR text differs): Both parties agree that Party B shall pay Party A the Deposit equal to the rent of one month in an amount of RMB85,330 when Party A hands over the Premises.
- [services_charges] ~line 77 (OCR text differs): During the tenancy, Party B shall bear the costs of water, electricity, gas, air-condition, telecom, equipments, parking and property management relating to the use of the Premises.
- [landlord_repairs] ~line 83 (OCR text differs): During the tenancy, in the event that Party B discovers any damage or breakdown of the Premises and accessory facilities, it shall notify Party A promptly for reparation. Party A shall repair them within 2 days from the date of receipt of the notice. If Party A fails to repair in time, Party B may repair them at the cost of Party A.
- [reinstatement_clause] ~line 33 (OCR text differs): Party B shall return the Premises to Party A on the date of the expiration of the tenancy unless Party A agrees to renew the lease. If Party B fails to return the Premises punctually without the consent of Party A, it shall pay double of the rent to Party A during the period of occupation of the Premises.
- [reinstatement_clause] ~line 100 (OCR text differs): Party B shall return the Premises in a condition consistent with the Premises having been used normally. Party A shall inspect the Premises when the Premises are returned and the parties hereto shall settle the fees that they are respectively responsible for.
- [break_option] ~line 122 (OCR text differs): Both parties agree that if any of the following events occurs, either party may inform the other party upon a written notice to terminate this Contract. The defaulting party shall pay the other party a penalty as liquidated damages equal to two times of the monthly rent. If the said liquidate damages are insufficient to make up for the losses suffered by the other party, the defaulting party shall further compensate for the balance thereof:
- [break_option] ~line 127 (OCR text differs): (1) Having failed to hand over the Premises punctually, Party A again fails to hand over the same within 15 days from the date of Party B’s written demand.
- [break_option] ~line 130 (OCR text differs): (2) The Premises handed over by Party A fail to comply with the conditions as herein contained, which frustrates the purpose of the lease; or the Premises are defective and endanger the safety of Party B.
- [break_option] ~line 133 (OCR text differs): (3) Party B changes the usage of the Premises without written consent of Party A, which causes damage to the Premises.
- [break_option] ~line 134 (OCR text differs): (4) The main structure of the Premises is damaged at fault of Party B.
- [break_option] ~line 136 (OCR text differs): (5) Party B sublets the Premises, transfers the leasing right of the Premises or exchanges with a third party their respective leased premises without permission.
- [break_option] ~line 138 (OCR text differs): (6) Party B fails to pay the rent for 1 month.
- [landlord_repairs] ~line 142 (OCR text differs): In the event that the Premises have been defective by the time of handing over, Party A shall repair the Premises within three days from the date of handing over. If failed to repair the Premises punctually, Party A shall reduce the rent and amend the provisions in relation to the rent.
