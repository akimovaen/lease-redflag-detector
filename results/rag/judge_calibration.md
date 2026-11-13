# Judge calibration

The answer judge (`prompts/judge/answer_v1.md`) against the lawyer's grades of 12 answers of `2026-11-11_haiku-v3` (`evals/judge_calibration.toml`).

## Key facts

46 grades, exact agreement 0.74, Cohen's kappa 0.14.

| Lawyer \ judge | present | partial | missing |
|---|---|---|---|
| present | 32 | 5 | 0 |
| partial | 3 | 1 | 0 |
| missing | 4 | 0 | 1 |

## Changed clause

12 grades, exact agreement 0.58, Cohen's kappa 0.25.

| Lawyer \ judge | good | minor_edits |
|---|---|---|
| good | 5 | 5 |
| minor_edits | 0 | 2 |

## Disagreements

| Flag | What | Lawyer | Judge | Judge's reason |
|---|---|---|---|---|
| f05 | fact 2: базова позиція — автоматична індексація без додаткової угоди, п. 2.1 | partial | present | Answer says the clause does not make indexation automatic, and the proposed clause makes it automatic without an additional agreement (п. 2.1 is not cited by number). |
| f07 | fact 4: запропонована редакція — Ф-2.3 з граничним розміром 10 % (7 % лише для якірного орендаря за погодженням генерального директора) | present | partial | The proposed clause uses a 10% cap, but it leaves out the 7% option for an anchor tenant with CEO approval, which the answer mentions only in the findings. |
| f07 | changed clause | good | minor_edits | The clause sets the cap at 10% as a placeholder, which fits the policy. It does not state the 7% exception for an anchor tenant approved by the CEO, so it needs minor edits. |
| f08 | fact 2: базова позиція — згода на власний розсуд Компанії, п. 5.1 | partial | present | Згадує п. 5.1 і необхідність письмової згоди, проте базову позицію «на власний розсуд Компанії» прямо формулює лише у зміненій редакції, а в findings говорить про обмеження дискреції. |
| f08 | fact 3: запропонована редакція — Ф-5.1, за потреби з Ф-5.4 (строк розгляду 15 робочих днів) | present | partial | Запропонована редакція містить згоду на власний розсуд (Ф-5.1), але строку розгляду 15 робочих днів (Ф-5.4) немає, і формули Ф-5.1 не названо. |
| f08 | changed clause | good | minor_edits | Редакція по суті правильна: згода на власний розсуд Орендодавця, але відсутня умова про строк розгляду 15 робочих днів за Ф-5.4, а також додано зайві положення; потрібні невеликі правки. |
| f10 | changed clause | good | minor_edits | The notice period of 10 working days is included, but «письмово» is missing, and the added term limit and liability for the sublessee go beyond the minimal edit that was expected. |
| f13 | fact 2: право орендаря ремонтувати за рахунок Компанії без її згоди неприйнятне, п. 6.4 | missing | present | The answer notes that the tenant may repair at the Company's expense and that this falls under p. 6.4, though it does not stress the absence of consent. |
| f13 | fact 3: ст. 776 ЦК: поточний ремонт — обов'язок наймача, якщо інше не встановлено договором | present | partial | The answer cites Art. 776 of the Civil Code but only says that current repair is not provided for by law by default. It does not state that current repair is the tenant's duty unless the contract says otherwise. |
| f13 | changed clause | good | minor_edits | The changed clause puts current repair on the Tenant and removes the tenant's right to repair at the Landlord's expense. But it adds a 30-day notice and a landlord capital-repair obligation that are not in F-6.1, and the answer does not tie it to F-6.1's text. It is right in substance but needs alignment with F-6.1. |
| f16 | fact 1: сплата податку на нерухомість і плати за землю Компанією як власником відповідає п. 7.1, якщо орендар відшкодовує свою частку у складі експлуатаційних витрат | present | partial | The answer says that under p. 7.1 these taxes belong to the share of operating costs the tenant reimburses, but it does not say that the landlord paying them is consistent with p. 7.1 provided the tenant reimburses its share; it treats the clause as a transfer. |
| f16 | fact 2: регулярне надання копій підтвердження сплати — поступка, ширша за право ознайомитися з первинними документами, п. 7.3 (Ф-7.4) | present | partial | The answer mentions the right to review documents (p. 7.3) as a permitted concession, but it does not say that regular provision of payment confirmation copies is a concession wider than that right. |
| f16 | fact 3: у пункті бракує умови про відшкодування цих податків орендарем | missing | present | The answer says the clause shifts the taxes onto the landlord without the tenant's reimbursement, which is the missing reimbursement condition. |
| f16 | fact 4: запропонована редакція — мінімальна правка: додати відшкодування частки пропорційно орендованій площі у складі експлуатаційних витрат (Ф-7.1) | missing | present | The answer proposes a clause with reimbursement of a share proportional to the leased area within operating costs, which is the core of the minimal fix. |
| f18 | fact 2: обмеження 50 % площі не робить умову допустимою: згода — на власний розсуд Компанії, п. 5.1 | partial | present | The answer says the clause is unacceptable regardless of the sublease size and, in the changed clause, consent is at the Landlord's own discretion; it cites п. 5.1 only in the risk line. |
| f22 | fact 3: Політика не має окремого правила про неможливість користуватися приміщенням через бойові дії | missing | present | Answer's section on points the sources do not settle says the sources do not define whether the tenant may terminate because of hostilities, missiles or power outages. |
| f22 | changed clause | good | minor_edits | The expected answer gives no explicit changed clause, but the answer's version, built on the p. 4.2 concession, would be needed as a fallback. It sets the minimum term, 6 months' notice and compensation for 3 or 6 months, and leaves the date as a placeholder. It does not address the war-related trigger, though removing it is consistent with the policy, so it can be pasted in with minor edits (for example, no mention of Ф-10.4 or the policy ban on unilateral termination being an exception). |
