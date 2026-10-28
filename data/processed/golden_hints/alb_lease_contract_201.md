# Hints for alb_lease_contract_201

Text: `data/texts/alb_lease_contract_201.txt` (823 words, dirt: none). Golden file: `data/golden/alb_lease_contract_201.json`.

Spans annotated by the ALeaseBERT authors. Values must be normalized to the schema (ISO dates, numbers, enums); quotes must be copied from the text file, not from here.

Red flag definitions:

- landlord_repairs: the landlord bears repairs or maintenance beyond the structure of the building, e.g. building systems, facilities or normal wear and tear.
- service_charges_limited: the landlord bears operating costs (management fees, utilities, taxes, insurance), they are included in the rent, or the tenant's share is capped or may be refused.
- tenant_break_option: the tenant may terminate before the end date on its own decision, with or without notice or a penalty. Not the landlord's right to terminate for the tenant's breach, and not a termination that needs the landlord's consent.
- indexation_limited: the rent cannot be increased, increases are capped, or they require the tenant's agreement.
- sublease_permitted: the tenant may sublet or assign without the landlord's consent, the landlord may not refuse or unreasonably withhold consent, or certain subtenants are pre-approved.

## ALeaseBERT entities

### lessor

- line 3: Lessor: Bozhou Fengyi Chinese Medicine Development and Research Institute (hereinafter referred to as Party A)
- line 48: Lessor: Bozhou Fengyi Chinese Medicine Development and Research Institute

### lessee

- line 4: Lessee: Anhui Xuelingxian Pharmaceutical Co., Ltd. (hereinafter referred to as Party B)
- line 50: Lessee: Anhui Xuelingxian Pharmaceutical Co., Ltd.
- line 51: Legal representative: Wang Shunli

### premises_address, area (leased_space)

- line 6: workshop (located at East Liuge Village, Weiwu Road, Bozhou, with the building area of 10000 square meters and usable area of 3000 square meters)

### start_date

- line 8: Aug 1, 2008

### end_date

- line 8: July 31, 2023

### end_date (expiration_date_of_lease)

- line 8: 15 years

### rent (term_of_payment)

- line 16: The rent is 1.2 million Yuan, and Party B shall pay 100000 Yuan to Party A before 15 of each month as the monthly rent.

## ALeaseBERT red flags

Check each one: is it risky for the landlord under the definitions above?

- [break_option] line 9: Party A has right to terminate the contract and takes back the house if one of the following situations occurred:
- [break_option] line 11: Party B transfers, subleases, lends, jointly operates, buys share or exchanges the house with others;
- [break_option] line 13: Party B uses the house to take illegal activities, which damages the public interests;
- [break_option] line 14: Party B has the priority to lease the house after the contract expires, and it can extend the lease term with negotiation of Party A if it cannot find the house promptly after the contract expires.
- [services_charges] line 16: The water & electricity fees shall be settled separately.
- [landlord_repairs] line 18: Party A takes charge of repairing of the house. Party A shall take the examination of the facilities, and it shall guarantee that there is no leakage, and the tap water, sewage and lighting, doors& windows are in good conditions, so as to ensure the normal and safe use of Party B.
- [landlord_repairs] line 19: The repair scope and standard shall be performed by Urban Construction Department (87) C.Z.G.Z.No. 13 Notice.
- [landlord_repairs] line 21: Through the negotiation of the two parties, Party A will contribute for the repairing work and organize the construction according to the maintenance scope.
- [change_of_control] line 25: If Party A transfers the house ownership to the third party according to the legal procedures, this contract continues to take effect to the new house owner without the agreement.
- [change_of_control] line 27: Party A shall notify Party B three months in advance of selling the house in the written form, and Party B has the priority to purchase the house under same conditions.
- [change_of_control] line 29: Party B shall get the approval of Party A if it intends to exchange the house with others, and Party A shall support the reasonable demand of Party B.
- [damage] line 32: If one party doesn’t comply with the terms of Article 4, the party shall compensate 50000 Yuan for another party.
- [services_charges] line 34: If Party A receives the additional fees except for the rent, Party B has right to refuse.
- [damage] line 40: The two parties take no responsibilities if the house is damaged or Party B has loss owing to the force majeure.
