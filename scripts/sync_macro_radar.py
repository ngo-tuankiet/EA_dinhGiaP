import sys
import os
import yaml
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from valuation.db.session import SessionLocalWrite
from valuation.db.models import MacroRadar
from valuation.config import PROJECT_ROOT

def sync_macro_radar():
    yaml_path = PROJECT_ROOT / "config" / "macro_radar.yaml"
    if not yaml_path.exists():
        print(f"File {yaml_path} does not exist!")
        return

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        
    indicators = data.get("macro_indicators", [])
    if not indicators:
        print("No macro indicators found in yaml configuration.")
        return

    db = SessionLocalWrite()
    try:
        # Clear old macro radar configs
        db.query(MacroRadar).delete()
        
        configs = []
        for ind in indicators:
            configs.append(MacroRadar(
                sector=ind.get("sector"),
                indicator_code=ind.get("indicator_code"),
                frequency=ind.get("frequency"),
                source=ind.get("source"),
                warn_low=ind.get("warn_low"),
                warn_high=ind.get("warn_high"),
                mapped_driver=ind.get("mapped_driver")
            ))
            
        db.add_all(configs)
        db.commit()
        print(f"SUCCESSfully synchronized {len(configs)} macro radar configurations to DB!")
    except Exception as e:
        db.rollback()
        print(f"FAILED to sync macro radar configurations: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    sync_macro_radar()
