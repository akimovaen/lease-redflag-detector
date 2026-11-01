# Hints for alb_lease_contract_54

Text: `data/texts/alb_lease_contract_54.txt` (7673 words, dirt: mixed_lang). Golden file: `data/golden/alb_lease_contract_54.json`.

Spans annotated by the ALeaseBERT authors. Values must be normalized to the schema (ISO dates, numbers, enums); quotes must be copied from the text file, not from here.

Red flag definitions:

- landlord_repairs: the landlord bears repairs or maintenance beyond the structure of the building, e.g. building systems, facilities or normal wear and tear.
- service_charges_limited: the landlord bears operating costs (management fees, utilities, taxes, insurance), they are included in the rent, or the tenant's share is capped or may be refused.
- tenant_break_option: the tenant may terminate before the end date on its own decision, with or without notice or a penalty. Not the landlord's right to terminate for the tenant's breach, and not a termination that needs the landlord's consent.
- indexation_limited: the rent cannot be increased, increases are capped, or they require the tenant's agreement.
- sublease_permitted: the tenant may sublet or assign without the landlord's consent, the landlord may not refuse or unreasonably withhold consent, or certain subtenants are pre-approved.

## ALeaseBERT entities

### document_type (type_lease)

- line 166: Section 676 (2) of the Civil Code and Section 9 (3) (a) of Act No. 116/1990 Coll., on lease and sublease of non-residential premises, as amended, shall not apply during this term
- line 228: This Contract shall be governed by the applicable provisions on lease agreement stipulated by Act No. 40/1964 Coll., the Civil Code, as amended, and Act No. 116/1990 Coll., on lease and sublease of non-residential premises, as amended.

### lessor

- line 4: Milan Gottwald
- line 5: Tax Id. No.: CZ 7502195327
- line 6: residing at: Náklo 334, Postal Code: 783 32

### lessee

- line 10: SENDIO s.r.o.
- line 11: Id. No.: 281 64 440
- line 12: Tax Id. No.: CZ28164440
- line 13: registered office at: Hranice, Olomoucká 306, Postal Code: 753 01
- line 14: registered in the Commercial Register kept by the Regional Court in Ostrava in Section C, Inset 43097

### start_date

- line 166: July 1, 2008

### end_date

- line 166: June 30, 2009

### rent (term_of_payment)

- line 67: The Parties have agreed on annual rent for the use of the Subject of the Lease, which shall be calculated as the amount of CZK 10,000,000.00 (in words: ten million Czech crowns), excl. VAT, minus the sum of the annual rents paid by all Further Tenants and all Other Tenants (as specified in Schedule No. 8 hereof) (hereinafter the “Annual Rent”).
- line 68: The Tenant shall pay the Rent monthly, always in the relevant calendar month to which the given Rent relates
- line 68: The Parties agree that the amount of the Monthly Rent for the month of July 2008 shall equal CZK 301,655.00 (in words: three hundred and one thousand six hundred and fifty-five Czech crowns) plus the applicable VAT; the amount of the Monthly Rent for the month of August 2008 shall equal CZK 376,655.00 (in words: three hundred and seventy-six thousand six hundred and fifty-five Czech crowns) plus the applicable VAT; and the amount of the Monthly Rent for each subsequent calendar month (i.e. September 2008 to June 2009) shall equal CZK 455,310.00 (in words: four hundred and fifty-five thousand three hundred and ten Czech crowns) plus the applicable VAT per calendar month. The Tenant shall always pay the Monthly Rent by a transfer to the Landlord’s account No. 6319656084/2700, kept by UniCredit Bank Czech Republic, a.s., branch in Zlín (hereinafter the “Landlord’s Account”). The day when the amount is credited to the Landlord’s Account shall be deemed to be the date of payment of the Monthly Rent. The Tenant shall pay the Monthly Rent on the basis of a tax document issued by the Landlord and within the set period of maturity, where the maturity of the tax document (invoice) shall equal 8 (eight) calendar days from the date of its delivery. The tax document shall contain all the requisites required by the applicable law. The first calendar day of the month in which the Monthly Rent is to be paid shall be the date of taxable supply.
- line 70: The Parties agree that the Tenant shall commence paying the Monthly Rent as of July 1, 2008. The Parties agree that also the first Monthly Rent in the amount of CZK 301,655.00 (in words: three hundred and one thousand six hundred and fifty-five Czech crowns) plus the applicable VAT shall be paid in accordance with Art. IV (2).

## ALeaseBERT red flags

Check each one: is it risky for the landlord under the definitions above?

- [services_charges] line 77: The Rent does not include payments for performances related to the use of the Subject of the Lease, including, without limitation, payments for supplies of water, gas, steam, electricity, telecommunication services and discharge of wastewater, etc.
- [landlord_repairs] line 124: The Landlord shall not be entitled to carry out any construction, i.e. construction of new buildings or extensions to the existing buildings, within the Premises.
- [sublease_permitted] line 193: The Tenant shall be entitled to sublease the Subject of the Lease only with the prior written consent of the Landlord. The Landlord agrees not to refuse the consent to the conclusion of the sublease contract without a serious reason.
- [change_of_control] line 213: The Tenant agrees to notify the Landlord, without undue delay, of any change in the structure of the shareholders of the Tenant (i.e. the shareholders of SENDIO s.r.o.). If the entity controlling the Tenant changes during the term of the lease and the new controlling person does not belong to the same business group to which the Tenant belongs as of the date of conclusion hereof, the Landlord shall be entitled to terminate this Contract. The Parties agree on a period of notice equal to 6 (six) months which shall commence on the first day of the month following after delivery of the notice by the Landlord to the Tenant.
