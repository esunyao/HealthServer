# Meal test navigation

Parent navigation: [tests AGENTS.md](../AGENTS.md).

- [test_meal_agent.py](test_meal_agent.py): preserved image, MCP, prompt and result-contract assertions.
- [test_meal_context_policy.py](test_meal_context_policy.py): capture schema, untrusted notes and empty evidence.
- [test_agent_loop.py](test_agent_loop.py): complete offline LangChain model/tool loops, rejected tools, invalid results and failures.
- [fake_model.py](fake_model.py): scripted chat model that records requests and tool bindings without a provider.
- [conftest.py](conftest.py): blocks real HTTP transports, DNS and tracing during these tests.
