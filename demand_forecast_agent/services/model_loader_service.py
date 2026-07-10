import os
import joblib
from pathlib import Path


class ModelLoaderService:

    _instance = None

    @classmethod
    def load(cls):

        if cls._instance:
            return cls._instance

        path = Path(
            os.getenv(
                "MODEL_PATH",
                "training_models/hybrid_model.pkl"
            )
        )

        if not path.exists():
            raise FileNotFoundError(
                f"Model missing: {path}"
            )

        cls._instance = joblib.load(path)

        return cls._instance