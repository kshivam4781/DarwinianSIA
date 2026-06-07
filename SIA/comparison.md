| Run | Mode | Best fitness | Mean fitness | Notes |
|-----|------|--------------|--------------|-------|
| run_201 | baseline | 0.133 | 0.133 | subset 30, 4/30 correct |
| run_311 | darwinian | 0.200 | 0.200 | gen 1, pop 2, elites [0], planning_style=hierarchical; reflection=True |
| run_311 | darwinian | 0.200 | 0.167 | gen 2, pop 2, elites [1], planning_style=hierarchical; reflection=True |
### Trait insights

- **planning_style**: hierarchical (2)
- **reflection**: True (2)
- **tool_strategy**: aggressive (2)
- **retry_policy**: error_specific (2)
- **memory**: failure_based (2)
- **confidence_threshold**: 0.61 (2)
- **prompt_structure**: minimal (2)
