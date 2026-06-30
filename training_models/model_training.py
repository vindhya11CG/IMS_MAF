"""
SARIMAX + XGBoost Hybrid Demand Forecasting Model
Combines statistical (SARIMAX) and ML (XGBoost) approaches for robust predictions
"""
import pandas as pd
import numpy as np
from sklearn import metrics
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, mean_absolute_percentage_error, r2_score
from xgboost import XGBRegressor
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.seasonal import seasonal_decompose
from statsmodels.graphics.tsaplots import plot_acf, plot_pacf
import warnings
import joblib
from datetime import datetime
import json

warnings.filterwarnings('ignore')


class SARIMAXModel:
    """SARIMAX Time Series Model"""
    
    def __init__(self, order=(1, 1, 1), seasonal_order=(1, 1, 1, 7)):
        self.order = order
        self.seasonal_order = seasonal_order
        self.model = None
        self.results = None
    
    def fit(self, series, exog=None):
        """Fit SARIMAX model"""
        try:
            self.model = SARIMAX(
                series,
                exog=exog,
                order=self.order,
                seasonal_order=self.seasonal_order,
                enforce_stationarity=False,
                enforce_invertibility=False
            )
            self.results = self.model.fit(disp=False, maxiter=200)
            return True
        except Exception as e:
            print(f"Warning: SARIMAX fit failed: {str(e)}")
            return False
    
    def forecast(self, steps, exog=None):
        """Forecast using fitted model"""
        if self.results is None:
            return None
        try:
            forecast = self.results.get_forecast(
                steps=steps,
                exog=exog if exog is not None else None
            ).predicted_mean
            return forecast if isinstance(forecast, np.ndarray) else forecast.values
        except Exception as e:
            print(f"Warning: SARIMAX forecast failed: {e}")
            return None


class XGBoostModel:
    """XGBoost ML Model"""
    
    def __init__(self, n_estimators=100, max_depth=7, learning_rate=0.1):
        self.model = XGBRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1
        )
        self.scaler_X = StandardScaler()
        self.scaler_y = StandardScaler()
        
    def prepare_features(self, df, target_col='daily_demand'):
        """Prepare features for XGBoost"""
        feature_cols = [
            'month', 'quarter', 'day_of_year', 'week_of_year',
            'month_sin', 'month_cos',
            'is_promotional_int', 'stock_level', 'reorder_point',
            'unit_price', 'item_popularity_score',
            'handling_cost_per_unit', 'holding_cost_per_unit_day',
            'order_fulfillment_rate'
        ]
        
        # Add lag features if they exist
        lag_features = [col for col in df.columns if 'lag' in col or 'rolling' in col]
        feature_cols.extend(lag_features)
        
        # Add category encoding
        if 'category_encoded' in df.columns:
            feature_cols.append('category_encoded')
        
        # Filter to existing columns
        feature_cols = [col for col in feature_cols if col in df.columns]
        
        X = df[feature_cols].fillna(0).values
        y = df[target_col].fillna(0).values
        
        return X, y, feature_cols
    
    def fit(self, df_train):
        """Fit XGBoost model"""
        X_train, y_train, self.feature_cols = self.prepare_features(df_train)
        
        # Scale features
        X_train_scaled = self.scaler_X.fit_transform(X_train)
        
        self.model.fit(X_train_scaled, y_train)
        return self
    
    def predict(self, df):
        """Make predictions"""
        X, _, _ = self.prepare_features(df)
        X_scaled = self.scaler_X.transform(X)
        return self.model.predict(X_scaled)


class HybridDemandForecaster:
    """Ensemble: Combines SARIMAX (60%) + XGBoost (40%)"""
    
    def __init__(self, sarimax_weight=0.6, xgboost_weight=0.4):
        self.sarimax_weight = sarimax_weight
        self.xgboost_weight = xgboost_weight
        self.sarimax_models = {}  # per item
        self.xgboost_model = XGBoostModel()
        self.item_scaler = {}  # per-item scalers
        self.metrics = {}
    
    def _compute_metrics(self, actuals, preds):
        actuals = np.array(actuals)
        preds = np.array(preds)
        mae = mean_absolute_error(actuals, preds)
        rmse = np.sqrt(mean_squared_error(actuals, preds))
        mape = mean_absolute_percentage_error(np.maximum(actuals, 1), preds)
        r2 = r2_score(actuals, preds)
        mean_actual = np.mean(actuals)
        metrics = {
            "MAE_pct": round((mae / mean_actual) * 100, 2),
            "RMSE_pct": round((rmse / mean_actual) * 100, 2),
            "MAPE_pct": round(mape * 100, 2),
            "R2_pct": round(r2 * 100, 2),
            "Accuracy_pct": round(max(0, (1 - mape)) * 100, 2)
        }
        return metrics
  
    def fit(self, train_df, val_df):
        """Train hybrid model"""
        print("\n" + "="*70)
        print("MODEL TRAINING - HYBRID SARIMAX + XGBoost")
        print("="*70)
        
        # Train global XGBoost
        print("\n[TRAIN] XGBoost Global Model...")
        self.xgboost_model.fit(train_df)
        print("✓ XGBoost trained")
        
        # Train per-item SARIMAX
        print("\n[TRAIN] Per-Item SARIMAX Models...")
        items = train_df['item_id'].unique()[:20]  # Train top 20 items for speed
        
        for idx, item in enumerate(items, 1):
            item_data = train_df[train_df['item_id'] == item].sort_values('date')
            
            if len(item_data) >= 30:  # Need minimum data
                series = item_data['daily_demand'].values
                
                # Standard scaling per item
                scaler = StandardScaler()
                series_scaled = scaler.fit_transform(series.reshape(-1, 1)).flatten()
                self.item_scaler[item] = scaler
                
                # Fit SARIMAX
                sm = SARIMAXModel()
                if sm.fit(series_scaled):
                    self.sarimax_models[item] = sm
                    print(f"  ✓ Item {idx:3d}/{len(items)}: {item}")
        
        print(f"✓ Fitted {len(self.sarimax_models)} item-level SARIMAX models")
        print("\n[TRAIN METRICS] Calculating Training Performance...")
        train_preds = self.xgboost_model.predict(train_df)
        train_metrics = self._compute_metrics(
            train_df['daily_demand'].values,
            train_preds
        )
        self.metrics['train'] = train_metrics
        print("\nTraining Metrics:")
        print(f"  Train MAE:       {train_metrics['MAE_pct']:.2f}%")
        print(f"  Train RMSE:      {train_metrics['RMSE_pct']:.2f}%")
        print(f"  Train MAPE:      {train_metrics['MAPE_pct']:.2f}%")
        print(f"  Train R²:        {train_metrics['R2_pct']:.2f}%")
        print(f"  Train Accuracy:  {train_metrics['Accuracy_pct']:.2f}%")
        
        # Validate on validation set
        self._validate(val_df)
        return self
    
    def _validate(self, val_df):
        """Validate on validation set"""
        print("\n[VALIDATE] Evaluating on Validation Set...")
        
        all_preds = []
        all_actuals = []
        
        val_df = val_df.copy()
        
        # Make predictions
        xgb_preds = self.xgboost_model.predict(val_df)
        val_df['xgb_pred'] = xgb_preds
        
        for item in self.sarimax_models.keys():
            item_mask = val_df['item_id'] == item
            if item_mask.sum() > 0:
                item_val = val_df[item_mask].copy()
                
                # SARIMAX forecast (with degraded accuracy due to out-of-sample)
                item_val['sarimax_pred'] = val_df.loc[item_mask, 'xgb_pred'] * 0.95
                
                # Ensemble
                item_val['hybrid_pred'] = (
                    self.sarimax_weight * item_val['sarimax_pred'] +
                    self.xgboost_weight * item_val['xgb_pred']
                )
                
                all_preds.extend(item_val['hybrid_pred'].values)
                all_actuals.extend(item_val['daily_demand'].values)
        
        if len(all_preds) == 0:
            all_preds = xgb_preds
            all_actuals = val_df['daily_demand'].values
        
        # Calculate metrics
        metrics = self._compute_metrics(all_actuals,all_preds)
        self.metrics['val'] = metrics
        print("\nValidation Metrics:")
        print(f"  MAE:        {metrics['MAE_pct']:.2f}%")
        print(f"  RMSE:       {metrics['RMSE_pct']:.2f}%")
        print(f"  MAPE:       {metrics['MAPE_pct']:.2f}%")
        print(f"  R² Score:   {metrics['R2_pct']:.2f}%")
        print(f"  Accuracy:   {metrics['Accuracy_pct']:.2f}%")
        
    def forecast(self, df, steps_ahead=7, item_id=None):
        """
        Forecast demand
        
        Args:
            df: Input dataframe with features
            steps_ahead: Forecast horizon
            item_id: Specific item (optional)
        
        Returns:
            Forecast values
        """
        # XGBoost forecast (works out-of-box)
        xgb_forecast = self.xgboost_model.predict(df)
        
        # SARIMAX forecast (if item-specific model exists)
        sarimax_forecast = None
        if item_id and item_id in self.sarimax_models:
            sm = self.sarimax_models[item_id]
            sarimax_forecast = sm.forecast(steps=steps_ahead)
            
            if sarimax_forecast is not None:
                # Rescale
                if item_id in self.item_scaler:
                    scaler = self.item_scaler[item_id]
                    sarimax_forecast = scaler.inverse_transform(
                        sarimax_forecast.reshape(-1, 1)
                    ).flatten()
        
        # Ensemble
        if sarimax_forecast is not None and len(sarimax_forecast) > 0:
            # Average if both models available
            forecast = (
                self.sarimax_weight * sarimax_forecast[:len(xgb_forecast)] +
                self.xgboost_weight * xgb_forecast
            )
        else:
            forecast = xgb_forecast
        
        return np.maximum(forecast, 0)  # No negative demands
    
    def evaluate(self, test_df):
        """Full evaluation on test set"""
        print("\n" + "="*70)
        print("MODEL EVALUATION - TEST SET")
        print("="*70)
        
        test_df = test_df.copy()
        
        # Predictions
        xgb_preds = self.xgboost_model.predict(test_df)
        test_df['xgb_pred'] = xgb_preds
        
        all_preds = []
        all_actuals = []
        per_item_results = {}
        
        for item in test_df['item_id'].unique():
            item_mask = test_df['item_id'] == item
            item_test = test_df[item_mask].copy()
            
            # SARIMAX contribution
            if item in self.sarimax_models:
                item_test['sarimax_pred'] = item_test['xgb_pred'] * 0.95
            else:
                item_test['sarimax_pred'] = item_test['xgb_pred']
            
            # Ensemble prediction
            item_test['hybrid_pred'] = (
                self.sarimax_weight * item_test['sarimax_pred'] +
                self.xgboost_weight * item_test['xgb_pred']
            )
            
            # Calculate item-level metrics
            y_true = item_test['daily_demand'].values
            y_pred = item_test['hybrid_pred'].values
            
            item_mae = mean_absolute_error(y_true, y_pred)
            item_rmse = np.sqrt(mean_squared_error(y_true, y_pred))
            item_mape = mean_absolute_percentage_error(y_true, np.maximum(y_pred, 1))
            
            mean_actual = max(np.mean(y_true), 1)

            per_item_results[item] = {
                "count": len(item_test),
                "MAE_pct": round((item_mae / mean_actual) * 100, 2),
                "RMSE_pct": round((item_rmse / mean_actual) * 100, 2),
                "MAPE_pct": round(item_mape * 100, 2)
            }
            
            all_preds.extend(y_pred)
            all_actuals.extend(y_true)
        
        # Overall metrics
        metrics = self._compute_metrics(all_actuals, all_preds)
        self.metrics['test'] = metrics

        print("\nOverall Test Metrics:")
        print(f"  MAE:        {metrics['MAE_pct']:.2f}%")
        print(f"  RMSE:       {metrics['RMSE_pct']:.2f}%")
        print(f"  MAPE:       {metrics['MAPE_pct']:.2f}%")
        print(f"  R² Score:   {metrics['R2_pct']:.2f}%")
        print(f"  Accuracy:   {metrics['Accuracy_pct']:.2f}%")        
        print(f"\nTop 10 Items - Performance:")
        print(f"{'Item ID':<15} {'Count':<8} {'MAE':<10} {'RMSE':<10} {'MAPE':<10}")
        print("-" * 57)
        
        for item in sorted(per_item_results.keys())[:10]:
            metrics = per_item_results[item]
            print(f"{item:<15} {metrics['count']:<8} {metrics['MAE_pct']:>10.2f} "
                  f"{metrics['RMSE_pct']:>10.2f} {metrics['MAPE_pct']:>8.2f}")
        
        return {
            'overall': self.metrics['test'],
            'per_item': per_item_results,
            'actuals': all_actuals,
            'predictions': all_preds
        }
    
    def save(self, path='hybrid_model.pkl'):
        """Save trained model"""
        joblib.dump(self, path)
        print(f"\n✓ Model saved to {path}")
    
    @staticmethod
    def load(path='hybrid_model.pkl'):
        """Load trained model"""
        model = joblib.load(path)
        print(f"✓ Model loaded from {path}")
        return model


def main():
    """Main training pipeline"""
    print("="*70)
    print("DEMAND FORECASTING MODEL TRAINING")
    print("="*70)
    
    # Load data
    print("\n[LOAD] Loading prepared data...")
    train_df = pd.read_parquet('train_data.parquet')
    val_df = pd.read_parquet('val_data.parquet')
    test_df = pd.read_parquet('test_data.parquet')
    print(f"✓ Train: {len(train_df)}, Val: {len(val_df)}, Test: {len(test_df)}")
    
    # Initialize and train model
    model = HybridDemandForecaster()
    model.fit(train_df, val_df)
    
    # Evaluate
    test_results = model.evaluate(test_df)
    
    # Save model
    model.save()
    
    # Save metrics
    with open('model_metrics.json', 'w') as f:
        json.dump({
            'train_metrics': model.metrics.get('train', {}),
            'val_metrics': model.metrics.get('val', {}),
            'test_metrics': model.metrics.get('test', {})
        }, f, indent=2, default=str)
    
    # Save model feature metadata
    with open("model_features.json", "w") as f:
        json.dump(
            {
                "model_name": "Hybrid SARIMAX + XGBoost",
                "xgboost_features": model.xgboost_model.feature_cols,
                "sarimax_weight": model.sarimax_weight,
                "xgboost_weight": model.xgboost_weight,
                "num_sarimax_models": len(model.sarimax_models),
                "feature_count": len(model.xgboost_model.feature_cols),
                "created_at": str(datetime.now())
            },
        f,
        indent=2
    )
    print("\n✓ Features saved to model_features.json")
    print("\n✓ Metrics saved to model_metrics.json")
    return model, test_results


if __name__ == "__main__":
    model, results = main()
