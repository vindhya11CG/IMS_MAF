"""Manual Azure OpenAI connectivity smoke test."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from demand_forecast_agent.services.azure_services import AzureConfigService


def main():
    cfg = AzureConfigService()

    print("=" * 60)
    print("AZURE OPENAI CONNECTIVITY SMOKE TEST")
    print("=" * 60)
    print(f"Deployment configured : {cfg.deployment!r}")
    print(f"Client initialized    : {cfg.client is not None}")
    print(f"Init error (if any)   : {cfg.init_error!r}")

    if cfg.client is None:
        print("\nFAILED: Azure client did not initialize. Check AZURE_OPENAI_* "
              "values in .env and that the `openai` package is installed.")
        sys.exit(1)

    print("\nSending a live test request to Azure OpenAI...")
    try:
        response = cfg.client.chat.completions.create(
            model=cfg.deployment,
            messages=[
                {"role": "user", "content": "Reply with exactly: Azure connection OK"}
            ],
            max_completion_tokens=20,
        )
        content = (response.choices[0].message.content or "").strip()
        print(f"\nSUCCESS - Azure responded: {content!r}")
        sys.exit(0)
    except Exception as e:
        print(f"\nFAILED - Azure call raised an exception:\n  {type(e).__name__}: {e}")
        print("\nCheck: AZURE_OPENAI_ENDPOINT (must be the full resource URL), "
              "AZURE_OPENAI_API_KEY, and that AZURE_OPENAI_DEPLOYMENT matches an "
              "actual deployment name in your Azure resource (not the base model name).")
        sys.exit(1)


if __name__ == "__main__":
    main()
