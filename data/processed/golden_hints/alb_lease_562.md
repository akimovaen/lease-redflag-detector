# Hints for alb_lease_562

Text: `data/texts/alb_lease_562.txt` (6990 words, dirt: mixed_lang). Golden file: `data/golden/alb_lease_562.json`.

Spans annotated by the ALeaseBERT authors. Values must be normalized to the schema (ISO dates, numbers, enums); quotes must be copied from the text file, not from here.

Red flag definitions:

- landlord_repairs: the landlord bears repairs or maintenance beyond the structure of the building, e.g. building systems, facilities or normal wear and tear.
- service_charges_limited: the landlord bears operating costs (management fees, utilities, taxes, insurance), they are included in the rent, or the tenant's share is capped or may be refused.
- tenant_break_option: the tenant may terminate before the end date on its own decision, with or without notice or a penalty. Not the landlord's right to terminate for the tenant's breach, and not a termination that needs the landlord's consent.
- indexation_limited: the rent cannot be increased, increases are capped, or they require the tenant's agreement.
- sublease_permitted: the tenant may sublet or assign without the landlord's consent, the landlord may not refuse or unreasonably withhold consent, or certain subtenants are pre-approved.

## ALeaseBERT entities

### premises_address, area (leased_space)

- line 265: Within the property located at:
- line 266: 8-14 RUE GRAMONT
- line 267: 14 RUE DU 4 SEPTEMBRE
- line 268: 75002 PARIS

### start_date

- line 317: “The current lease has been granted and agreed upon for the duration of nine consecutive years and two full months, which shall begin from the effective date as stipulated in Chapter V2.

### end_date

- line 317: It shall end under the conditions described in Article L.145.9 of the Commercial Code (formerly Article 5 of the September 30, 1953 decree).

### rent (term_of_payment)

- line 293: Annual base rent, excluding taxes and service charges: 3,450,000 € (THREE MILLION FOUR HUNDRED FIFTY THOUSAND EUROS):
- line 294: A rent-free period, excluding services charges, of eleven months has been granted to the Lessor.
- line 295: Payment of the first term shall therefore occur on: December 1, 2006
- line 296: For the period beginning on December 1, 2006 and ending December 31, 2006

### indexation (indexation_rent)

- line 308: Latest INSEE index to date – publication in the Official Journal upon the effective entry date of the premises, i.e. index 1269 (4th quarter 2004). First revision: January 1, 2007.

## ALeaseBERT red flags

Check each one: is it risky for the landlord under the definitions above?

- [services_charges] line 299: “The Lessee shall undertake and directly finance the service charges required for the operation of the property. The Lessor shall be assured that the Lessee has contracted on a regular basis various maintenance work for the property by providing a copy of the signed contracts to the Lessor once they have been signed.
- [services_charges] line 300: In the event that these contracts are modified or cancelled, the Lessor must be notified within fifteen days. The Lessor may verify on a yearly basis that these contracts are produced to have a legal and technical effect and verify their proper execution. The Lessor shall conduct two visits per year for monitoring.
- [services_charges] line 301: The quarterly payment must include administrative fees, miscellaneous technical fees paid by the Lessee to the Lessor in the amount of 25,000 €, excluding taxes.
- [services_charges] line 302: The settlement shall take place once a year.
- [break_option] line 318: The Lessee shall have the authority to give notice “at the end of the third triennial period and two months” by notifying the Lessor by an extrajudicial document, at least six months prior to the expiration for the current period.”
- [sublease_permitted] line 340: “However by derogation from the above paragraph, the Lessee shall have the authority to partially sublet the premises to one or more companies in which the Lessee holds at least 50% of their assets, in which case the Lessee must notify the Lessor in advance of all sublease contracts signed in accordance with this authorization”.
