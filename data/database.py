"""
MongoDB Atlas database layer for Chuky Bot.

Manages connections and CRUD operations for:
- backtests: Complete backtest results (config, metrics, equity curve)
- trades: Individual trade records with FVG associations
- fvgs: Detected FVGs by timeframe with active/invalidated status
- market_data: Cached OHLCV data to reduce API calls
- bot_config: Saved bot configurations

Connection string is stored in config/settings.py.
"""
import os
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import pandas as pd
import numpy as np

# Ensure project root is importable
ROOT_DIR = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT_DIR)

try:
    from pymongo import MongoClient, ASCENDING, DESCENDING
    from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
    PYMONGO_AVAILABLE = True
except ImportError:
    PYMONGO_AVAILABLE = False

from config.settings import MONGODB_URI, MONGODB_DB_NAME


# =============================================================================
# Singleton Connection
# =============================================================================
_client: Optional[Any] = None
_db: Optional[Any] = None


def get_db():
    """
    Returns the MongoDB database instance (singleton pattern).
    Creates the connection on first call, reuses it thereafter.
    """
    global _client, _db

    if not PYMONGO_AVAILABLE:
        print("[DB] WARNING: pymongo not installed. Database features disabled.")
        return None

    if _db is not None:
        return _db

    if not MONGODB_URI:
        print("[DB] WARNING: MONGODB_URI no configurado. Database features disabled.")
        return None

    try:
        _client = MongoClient(
            MONGODB_URI,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
        )
        # Test connection
        _client.admin.command("ping")
        _db = _client[MONGODB_DB_NAME]
        print(f"[DB] Connected to MongoDB Atlas: {MONGODB_DB_NAME}")
        _ensure_indexes()
        return _db
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        print(f"[DB] WARNING: Could not connect to MongoDB: {e}")
        print("[DB] Running in offline mode — data will not persist.")
        return None
    except Exception as e:
        print(f"[DB] WARNING: MongoDB connection error: {e}")
        return None


def _ensure_indexes():
    """Create indexes for optimal query performance."""
    if _db is None:
        return
    try:
        # Backtests: query by date
        _db.backtests.create_index([("created_at", DESCENDING)])
        _db.backtests.create_index([("config_name", ASCENDING)])

        # Trades: query by time and direction
        _db.trades.create_index([("backtest_id", ASCENDING)])
        _db.trades.create_index([("timestamp", DESCENDING)])
        _db.trades.create_index([("direction", ASCENDING)])

        # FVGs: query by timeframe and status
        _db.fvgs.create_index([("backtest_id", ASCENDING)])
        _db.fvgs.create_index([("timeframe", ASCENDING), ("status", ASCENDING)])
        _db.fvgs.create_index([("timestamp", DESCENDING)])

        # Market data: query by symbol, interval, date
        _db.market_data.create_index([
            ("symbol", ASCENDING),
            ("interval", ASCENDING),
            ("start", ASCENDING),
            ("end", ASCENDING),
        ])

        # Bot config
        _db.bot_config.create_index([("name", ASCENDING)], unique=True)

        print("[DB] Indexes ensured.")
    except Exception as e:
        print(f"[DB] Warning: Could not create indexes: {e}")


# =============================================================================
# Backtest Operations
# =============================================================================
def save_backtest(
    config: dict,
    metrics: dict,
    trades_df: pd.DataFrame,
    equity_df: pd.DataFrame,
    fvgs_data: List[dict] = None,
    period_name: str = "Backtest",
) -> Optional[str]:
    """
    Save a complete backtest result to MongoDB.

    Returns the inserted document ID as string, or None if DB unavailable.
    """
    db = get_db()
    if db is None:
        return None

    try:
        # Convert DataFrames to serializable format
        trades_list = []
        if not trades_df.empty:
            trades_serializable = trades_df.copy()
            for col in trades_serializable.columns:
                if trades_serializable[col].dtype == "datetime64[ns]" or "time" in col.lower():
                    trades_serializable[col] = trades_serializable[col].astype(str)
            trades_list = trades_serializable.to_dict(orient="records")

        equity_list = []
        if not equity_df.empty:
            equity_serializable = equity_df.copy()
            for col in equity_serializable.columns:
                if equity_serializable[col].dtype == "datetime64[ns]":
                    equity_serializable[col] = equity_serializable[col].astype(str)
            equity_list = equity_serializable.to_dict(orient="records")

        # Clean metrics (convert numpy types to native Python)
        clean_metrics = _clean_for_mongo(metrics)
        clean_config = _clean_for_mongo(config)

        doc = {
            "period_name": period_name,
            "config_name": config.get("name", "Unknown"),
            "config": clean_config,
            "metrics": clean_metrics,
            "trades": trades_list,
            "equity_curve": equity_list,
            "fvgs": fvgs_data or [],
            "total_trades": len(trades_list),
            "total_pnl": float(metrics.get("total_pnl", 0)),
            "created_at": datetime.utcnow(),
        }

        result = db.backtests.insert_one(doc)
        backtest_id = str(result.inserted_id)
        print(f"[DB] Backtest saved: {backtest_id}")

        # Also save individual trades with backtest reference
        if trades_list:
            for trade in trades_list:
                trade["backtest_id"] = backtest_id
            db.trades.insert_many(trades_list)

        # Save FVGs with backtest reference
        if fvgs_data:
            for fvg in fvgs_data:
                fvg["backtest_id"] = backtest_id
            db.fvgs.insert_many(fvgs_data)

        return backtest_id

    except Exception as e:
        print(f"[DB] Error saving backtest: {e}")
        return None


def list_backtests(limit: int = 20) -> List[dict]:
    """List recent backtests (summary only, no full data)."""
    db = get_db()
    if db is None:
        return []

    try:
        cursor = db.backtests.find(
            {},
            {
                "period_name": 1, "config_name": 1, "total_trades": 1,
                "total_pnl": 1, "created_at": 1,
                "metrics.win_rate": 1, "metrics.sharpe_ratio": 1,
                "metrics.profit_factor": 1,
            }
        ).sort("created_at", DESCENDING).limit(limit)
        return [_stringify_id(doc) for doc in cursor]
    except Exception as e:
        print(f"[DB] Error listing backtests: {e}")
        return []


def load_backtest(backtest_id: str) -> Optional[dict]:
    """Load a complete backtest by ID."""
    db = get_db()
    if db is None:
        return None

    try:
        from bson import ObjectId
        doc = db.backtests.find_one({"_id": ObjectId(backtest_id)})
        if doc:
            return _stringify_id(doc)
        return None
    except Exception as e:
        print(f"[DB] Error loading backtest: {e}")
        return None


def delete_backtest(backtest_id: str) -> bool:
    """Delete a backtest and its associated trades/fvgs."""
    db = get_db()
    if db is None:
        return False

    try:
        from bson import ObjectId
        db.backtests.delete_one({"_id": ObjectId(backtest_id)})
        db.trades.delete_many({"backtest_id": backtest_id})
        db.fvgs.delete_many({"backtest_id": backtest_id})
        return True
    except Exception as e:
        print(f"[DB] Error deleting backtest: {e}")
        return False


# =============================================================================
# FVG Operations
# =============================================================================
def save_fvgs(fvgs: List[dict], backtest_id: str = None) -> bool:
    """Save a batch of FVG records."""
    db = get_db()
    if db is None:
        return False

    try:
        for fvg in fvgs:
            fvg["backtest_id"] = backtest_id
            fvg["saved_at"] = datetime.utcnow()
        if fvgs:
            db.fvgs.insert_many(fvgs)
        return True
    except Exception as e:
        print(f"[DB] Error saving FVGs: {e}")
        return False


def get_fvgs_for_backtest(backtest_id: str) -> List[dict]:
    """Retrieve all FVGs associated with a backtest."""
    db = get_db()
    if db is None:
        return []

    try:
        cursor = db.fvgs.find({"backtest_id": backtest_id})
        return [_stringify_id(doc) for doc in cursor]
    except Exception as e:
        print(f"[DB] Error loading FVGs: {e}")
        return []


# =============================================================================
# Market Data Cache
# =============================================================================
def cache_market_data(
    symbol: str,
    interval: str,
    start: str,
    end: str,
    df: pd.DataFrame,
) -> bool:
    """Cache OHLCV data in MongoDB to reduce API calls."""
    db = get_db()
    if db is None:
        return False

    try:
        records = df.reset_index().to_dict(orient="records")
        # Convert timestamps
        for r in records:
            for k, v in r.items():
                if isinstance(v, pd.Timestamp):
                    r[k] = v.isoformat()
                elif isinstance(v, (np.integer,)):
                    r[k] = int(v)
                elif isinstance(v, (np.floating,)):
                    r[k] = float(v)

        doc = {
            "symbol": symbol,
            "interval": interval,
            "start": start,
            "end": end,
            "data": records,
            "count": len(records),
            "cached_at": datetime.utcnow(),
        }

        # Upsert: replace existing cache for same params
        db.market_data.replace_one(
            {"symbol": symbol, "interval": interval, "start": start, "end": end},
            doc,
            upsert=True,
        )
        return True
    except Exception as e:
        print(f"[DB] Error caching market data: {e}")
        return False


def load_cached_market_data(
    symbol: str,
    interval: str,
    start: str,
    end: str,
    max_age_hours: int = 24,
) -> Optional[pd.DataFrame]:
    """
    Load cached market data if available and not expired.

    Returns None if cache miss or expired.
    """
    db = get_db()
    if db is None:
        return None

    try:
        doc = db.market_data.find_one({
            "symbol": symbol,
            "interval": interval,
            "start": start,
            "end": end,
        })

        if doc is None:
            return None

        # Check age
        cached_at = doc.get("cached_at", datetime.min)
        if datetime.utcnow() - cached_at > timedelta(hours=max_age_hours):
            return None  # Cache expired

        records = doc.get("data", [])
        if not records:
            return None

        df = pd.DataFrame(records)

        # Restore datetime index
        datetime_col = None
        for col in ["Date", "Datetime", "datetime", "index"]:
            if col in df.columns:
                datetime_col = col
                break

        if datetime_col:
            df[datetime_col] = pd.to_datetime(df[datetime_col])
            df.set_index(datetime_col, inplace=True)

        return df
    except Exception as e:
        print(f"[DB] Error loading cached data: {e}")
        return None


# =============================================================================
# Bot Config Operations
# =============================================================================
def save_bot_config(config: dict) -> bool:
    """Save or update a bot configuration."""
    db = get_db()
    if db is None:
        return False

    try:
        clean = _clean_for_mongo(config)
        clean["updated_at"] = datetime.utcnow()
        name = clean.get("name", "Default")
        db.bot_config.replace_one(
            {"name": name},
            clean,
            upsert=True,
        )
        return True
    except Exception as e:
        print(f"[DB] Error saving config: {e}")
        return False


def list_bot_configs() -> List[dict]:
    """List all saved bot configurations."""
    db = get_db()
    if db is None:
        return []

    try:
        cursor = db.bot_config.find().sort("updated_at", DESCENDING)
        return [_stringify_id(doc) for doc in cursor]
    except Exception as e:
        print(f"[DB] Error listing configs: {e}")
        return []


def load_bot_config(name: str) -> Optional[dict]:
    """Load a bot configuration by name."""
    db = get_db()
    if db is None:
        return None

    try:
        doc = db.bot_config.find_one({"name": name})
        if doc:
            return _stringify_id(doc)
        return None
    except Exception as e:
        print(f"[DB] Error loading config: {e}")
        return None


# =============================================================================
# Utility Functions
# =============================================================================
def _clean_for_mongo(obj):
    """Recursively convert numpy/pandas types to native Python for MongoDB."""
    if isinstance(obj, dict):
        return {k: _clean_for_mongo(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_clean_for_mongo(item) for item in obj]
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def _stringify_id(doc: dict) -> dict:
    """Convert MongoDB _id (ObjectId) to string."""
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


def get_db_status() -> dict:
    """Return connection status info for the dashboard."""
    db = get_db()
    if db is None:
        return {"connected": False, "message": "Not connected to MongoDB"}

    try:
        stats = {
            "connected": True,
            "database": MONGODB_DB_NAME,
            "backtests_count": db.backtests.count_documents({}),
            "trades_count": db.trades.count_documents({}),
            "fvgs_count": db.fvgs.count_documents({}),
            "configs_count": db.bot_config.count_documents({}),
        }
        return stats
    except Exception as e:
        return {"connected": False, "message": str(e)}
