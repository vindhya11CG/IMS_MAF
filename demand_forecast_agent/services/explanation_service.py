from .azure_config_service import (
    AzureConfigService
)


class ExplanationService:

    def __init__(self):

        cfg = (
            AzureConfigService()
        )

        self.client = (
            cfg.client
        )

        self.model = (
            cfg.deployment
        )

    def execute(
        self,
        sku,
        forecast,
        confidence
    ):

        r = (
            self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role":"system",
                        "content":"""
Explain inventory demand.
Short.
Business language.
"""
                    },
                    {
                        "role":"user",
                        "content":
                        f"""
SKU:
{sku}

Forecast:
{forecast}

Confidence:
{confidence}
"""
                    }
                ]
            )
        )

        return (
            r.choices[0]
            .message
            .content
        )