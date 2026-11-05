# Chunking comparison

Structural: sections and clauses, target 350 / max 450 tokens. Fixed: windows of 350 tokens with 50 tokens of overlap.

| Document | Chunking | Chunks | Median tokens | Units | Units kept whole | Chunks starting mid-sentence | Chunks citable by section |
|---|---|---|---|---|---|---|---|
| policy_2026 | structural | 12 | 298 | 53 | 100% | 0% | 92% |
| policy_2026 | fixed | 12 | 350 | 53 | 92% | 92% | 0% |
| clause_library_2026 | structural | 39 | 64 | 42 | 100% | 0% | 97% |
| clause_library_2026 | fixed | 13 | 350 | 42 | 90% | 69% | 0% |
| civil_code | structural | 53 | 83 | 158 | 100% | 0% | 100% |
| civil_code | fixed | 21 | 350 | 158 | 94% | 81% | 0% |
| law_157_ix | structural | 73 | 343 | 168 | 100% | 12% | 99% |
| law_157_ix | fixed | 81 | 350 | 168 | 90% | 90% | 0% |
| lease_06288 | structural | 39 | 337 | 40 | 100% | 3% | 97% |
| lease_06288 | fixed | 41 | 350 | 40 | 85% | 88% | 0% |
| lease_83432 | structural | 62 | 261 | 98 | 99% | 5% | 97% |
| lease_83432 | fixed | 54 | 350 | 98 | 78% | 50% | 0% |
| **all** | **structural** | 278 | | 559 | **100%** | **5%** | **98%** |
| **all** | **fixed** | 222 | | 559 | **89%** | **78%** | **0%** |
