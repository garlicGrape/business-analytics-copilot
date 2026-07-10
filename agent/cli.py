"""Quick interactive test harness: python -m agent.cli"""

from .agent import agent, extract_text


def main():
    thread_id = "cli-session"
    print("Business Analytics Copilot (type 'exit' to quit)")
    while True:
        user_input = input("> ")
        if user_input.strip().lower() in {"exit", "quit"}:
            break
        result = agent.invoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config={"configurable": {"thread_id": thread_id}},
        )
        print(extract_text(result["messages"][-1].content))


if __name__ == "__main__":
    main()
