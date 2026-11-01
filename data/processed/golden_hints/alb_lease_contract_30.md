# Hints for alb_lease_contract_30

Text: `data/texts/alb_lease_contract_30.txt` (2998 words, dirt: encoding;template_blanks). Golden file: `data/golden/alb_lease_contract_30.json`.

Spans annotated by the ALeaseBERT authors. Values must be normalized to the schema (ISO dates, numbers, enums); quotes must be copied from the text file, not from here.

Red flag definitions:

- landlord_repairs: the landlord bears repairs or maintenance beyond the structure of the building, e.g. building systems, facilities or normal wear and tear.
- service_charges_limited: the landlord bears operating costs (management fees, utilities, taxes, insurance), they are included in the rent, or the tenant's share is capped or may be refused.
- tenant_break_option: the tenant may terminate before the end date on its own decision, with or without notice or a penalty. Not the landlord's right to terminate for the tenant's breach, and not a termination that needs the landlord's consent.
- indexation_limited: the rent cannot be increased, increases are capped, or they require the tenant's agreement.
- sublease_permitted: the tenant may sublet or assign without the landlord's consent, the landlord may not refuse or unreasonably withhold consent, or certain subtenants are pre-approved.

## ALeaseBERT entities

### lessor

- line 8: Shenzhen HYT Science &Technology Co., Ltd.
- line 9: Address: HYT Tower, Shenzhen Hi-Tech Industrial Park North, Beihuan RD, Shenzhen
- line 10: Post Code: 518057
- line 11: Authorized Agent: Wu Mei
- line 13: Post Code: 518057

### lessee

- line 14: Fiberxon Technology (Shenzhen) Inc.
- line 15: Address: 4th floor, Weiyong Building, Kefa Road No.10, Science & Technology Park Nanshan District, Shenzhen
- line 16: Post Code: 518057
- line 17: Business License or ID card No.: Enterprise of Exclusive Investment in Shenzhen No. 307727A.
- line 18: Authorized Agent: Xu Yi
- line 20: Post Code: 518057

### start_date

- line 34: November 20, 2004

### end_date

- line 34: November 19, 2007

## ALeaseBERT red flags

Check each one: is it risky for the landlord under the definitions above?

- [guarantee_transferable] line 42: While handing over The Premises, Party A has the right to ask for the lease deposit of less than three months’ rent that is 82,600 RMB.
- [services_charges] line 54: During the lease term, Party A shall be responsible for the land use fees of The Premises, its caused taxes, housing lease administrative fees as well as fees; Party B shall pay for electricity and water supply fees, sanitary fees, house (building) administrative fees, air conditioning fees and other fees that are caused by the usage of The Premises.
- [landlord_repairs] line 62: In case Party B’s inappropriate or unreasonable use impedes security of The Premises, or causes damages or troubles to The Premises, Party B shall make a timely notification to Party A and is responsible for the repairs or compensation. If Party B refuses for the repairs or compensation, it will be put on record by the contract registration bureau and Party A will repair for Party B who shall pay for the relevant repairing expenses.
- [sublease_permitted] line 70: However, within the lease term, Party B can, with the written consent of Party A, go through transfer registration procedures at the housing lease administrative bureau with the written proof of Party A’s consent. The term for transfer lease shall not exceed the lease term stipulated in this contract.
- [change_of_control] line 73: Within the validity period of this contract, Party A shall transfer fully or partially its owner’s rights towards The Premises and notify the transfer to Party B within written notice one month in advance. Party B has the right of preemption in equal conditions.
- [sublease_permitted] line 74: In case The Premises is assigned to third parties, Party A shall tell the assignee to continue to fulfill this contract while signing the assignment contract.
- [reinstatement_clause] line 105: Upon the termination of this contract, Party B shall move from The Premises and give it back within five days. Additionally, Party B shall guarantee that The Premises and its subsidiary facilities are in a perfect state (normal wear and tear not included). At the same time, all the expenses that Party B is liable for shall be paid off and procedures for transfer shall be handled.
