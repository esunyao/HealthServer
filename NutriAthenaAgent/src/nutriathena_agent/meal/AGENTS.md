# Meal analysis navigation

Parent navigation: [package AGENTS.md](../AGENTS.md).

- [agent.py](agent.py): LangChain agent construction and the two context tools.
- [runner.py](runner.py): one attempt, image loading, tool presentation checks and cleanup; the runner protocol is in [execution/ports.py](../execution/ports.py).
- [input.py](input.py): evidence loading, untrusted input data and final text extraction.
- [prompt.py](prompt.py): maintained skill selection and prompt assembly; asset paths come from [runtime/paths.py](../runtime/paths.py).
- [contract.py](contract.py): strict analysis and review result validation.
- [Meal tests](../../../tests/meal/AGENTS.md): preserved assertions and offline model/tool loops.
