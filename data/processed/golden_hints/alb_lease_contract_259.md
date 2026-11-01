# Hints for alb_lease_contract_259

Text: `data/texts/alb_lease_contract_259.txt` (2976 words, dirt: none). Golden file: `data/golden/alb_lease_contract_259.json`.

Spans annotated by the ALeaseBERT authors. Values must be normalized to the schema (ISO dates, numbers, enums); quotes must be copied from the text file, not from here.

Red flag definitions:

- landlord_repairs: the landlord bears repairs or maintenance beyond the structure of the building, e.g. building systems, facilities or normal wear and tear.
- service_charges_limited: the landlord bears operating costs (management fees, utilities, taxes, insurance), they are included in the rent, or the tenant's share is capped or may be refused.
- tenant_break_option: the tenant may terminate before the end date on its own decision, with or without notice or a penalty. Not the landlord's right to terminate for the tenant's breach, and not a termination that needs the landlord's consent.
- indexation_limited: the rent cannot be increased, increases are capped, or they require the tenant's agreement.
- sublease_permitted: the tenant may sublet or assign without the landlord's consent, the landlord may not refuse or unreasonably withhold consent, or certain subtenants are pre-approved.

## ALeaseBERT entities

### lessor

- line 5: Lessor: China National Precision Machinery I&E Corp. Beijing Aerospace CPMIEC Building
- line 11: China National Precision Machinery I&E Corp. Beijing Aerospace CPMIEC Building (hereinafter referred to as “Party A”)
- line 12: Responsible Person: Zhang Hong
- line 13: Address: No.30 Haidian South Road, Beijing, China
- line 14: Postal code: 10080
- line 96: China National Precision Machinery I&E Corp. Beijing Aerospace CPMIEC Building
- line 97: Address: No.30 Haidian South Road
- line 98: Telephone: 62626112
- line 99: Bank: Hangtian Branch of Beijing Bank
- line 100: Account No.: 01090372800120111017413

### lessee

- line 6: Lessee: Fortune Software (Beijing) Co., Ltd.
- line 15: Lessee: Fortune Software (Beijing) Co., Ltd. (hereinafter referred to as “Party B”)

### premises_address, area (leased_space)

- line 22: Room 626(6th Floor of China National Precision Machinery I&E Corp. Beijing Aerospace CPMIEC Building, No.30 Haidian South Road, Haidian District Beijing) with an area of structure of 190.71 square meters.

### start_date

- line 24: July 30 th 2009

### end_date

- line 24: July 29th, 2010

### end_date (expiration_date_of_lease)

- line 24: The term of lease is 12 months

### rent (term_of_payment)

- line 27: The rent applicable to the subject matter of lease shall be RMB 108 per square meter per month. The total rent for each month shall be RMB 20596.68.
- line 28: The rent shall be calculated from the commencing date of this Contract.
- line 37: The method of rent collection of Party A is roll-up. Party B shall pay the rent of the month prior to 10 th of each month.

## ALeaseBERT red flags

Check each one: is it risky for the landlord under the definitions above?

- [right_of_first_refusal_to_lease] line 25: If Party A continues to lease the housing unit hereunder, Party B shall have the priority right upon the same conditions. Party B shall make written application for lease renewal within 2 months prior to expiration of the term. The rent for renewal and other fees shall be determined through negotiations.
- [services_charges] line 27: The property management fee shall be contained in the rent, including but not limited to central air-conditioning fee (cooling, heating and fresh air); cleaning fee for public area, external wall and washroom; three guarantees for the front land of the building; maintenance fee for public area, public facilities (water, electricity, heating, ventilation, cooling, telecom and fire protection), electricity fee for regular office use (non-operational electricity consumption) etc.
- [reinstatement_clause] line 29: The deadline of the rent shall be determined on the date when Party B restitutes the subject matter hereof, returns the key and delivers the subject matter to Party A.
- [break_option] line 39: Party A is entitled to terminate the Contract unilaterally and claim for the overdue payment in case Party B’s overdue payment in aggregate (including without limitation room rate, incidental expense, overdue fine, etc.) exceeds 65% of the deposit. Party B shall be responsible for any result incurred therefrom.
- [sublease_permitted] line 41: Party A shall not lease the subject housing unit to a third party.
- [landlord_repairs] line 42: Party A shall be responsible for repair and maintenance of electricity, air-conditioning, water supply, drainage and elevator; responsible for repair, maintenance, cleaning, refurbishment of the external wall, phone line, sewer, conduit, sanitary installation, down pipe and water installation, and the relevant fees to keep the aforesaid devices under normal operation (the devices and requirements installed by Party B shall be negotiated by the parties).
- [damage] line 62: In case of damages or direct losses due to reckless or neglect of Party B or its personnel, Party B shall be allowed to enter into the leased unit and repair damages or losses of the unit, expenses arising therefrom shall be borne by Party B.
- [break_option] line 80: In case Party B requires terminating the Contract after execution without using the unit, Party A shall not refund the deposit.
- [break_option] line 81: Provided Party B requires terminating the lease within the term of lease, Party A shall withhold the deposit as the liquidated damages.
- [break_option] line 82: In the event that Party A terminates the Contract due to its own while Party B does not commit default acts, Party A shall pay to Party B liquidated damages in an amount equal to the deposit.
