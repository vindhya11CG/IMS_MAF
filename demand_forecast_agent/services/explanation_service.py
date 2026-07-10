from .azure_services import (
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

    def execute(self, sku, forecast, confidence):
        try:
            r = (
                self.client.chat.completions.create(

                model=self.model,

                messages=[

                    {

                        "role":
                        "system",

                        "content":
                        "Explain inventory forecast."

                    },

                    {

                        "role":
                        "user",

                        "content":

                        f"""
Product:
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

            return r.choices[0].message.content
        except Exception:
            return (

            f"""
Forecast:

{forecast}

Confidence:

{confidence}

Inventory planning recommended.
"""

        )