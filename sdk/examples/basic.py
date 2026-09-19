import asyncio
import os

from tracyn import ApprovalDeniedError, ApprovalTimeoutError, Tracyn

audit = Tracyn(
    api_key=os.environ["TRACYN_API_KEY"],
    agent_name="support-bot",
)


@audit.track(action_type="internal", action_name="summarize_ticket")
async def summarize_ticket(ticket_text: str, model: str = "claude-haiku-4-5-20251001") -> str:
    return f"Summary of: {ticket_text[:40]}..."


@audit.track(action_type="external", action_name="send_refund_email")
async def send_refund_email(to: str, amount_usd: float) -> dict:
    print(f"(pretend) emailing {to} about a ${amount_usd} refund")
    return {"sent": True}


async def main() -> None:
    summary = await summarize_ticket("Customer says the widget broke after two days...")
    print(summary)

    try:
        await send_refund_email("customer@example.com", 49.99)
    except ApprovalDeniedError as e:
        print(f"Refund blocked: {e}")
    except ApprovalTimeoutError as e:
        print(f"Refund auto-denied: {e}")

    audit.close()


if __name__ == "__main__":
    asyncio.run(main())
