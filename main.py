# main.py
import time
import random
from ai_core.orchestrator import Orchestrator
from ai_core.director_agent import DirectorAgent
from ai_core.publisher_agent import PublisherAgent

def main():
    print("==================================================")
    print(" GLOBAL NEXUS: Autonomous Mining & Production v3.0")
    print("==================================================")
    
    director = DirectorAgent()
    orchestrator = Orchestrator()
    publisher = PublisherAgent()
    
    # ▼ 設定エリア ▼
    # None にすれば「全自動マイニングモード（Trendsから取得）」
    # 文字列を入れれば「そのテーマ周辺のニッチ発掘モード」
    # 例: USER_SEED_TOPIC = "deep sea mining" 
    USER_SEED_TOPIC = "AI agent" 
    
    TARGET_LANGUAGES = ["en", "ja", "es"]
    
    iteration = 1
    
    while True:
        print(f"\n[System] Mining Cycle {iteration} Initiated...")
        
        # 1. Directorによる市場調査と戦略立案
        strategies = director.discover_targets(seed_topic=USER_SEED_TOPIC)
        
        if not strategies:
            print("[System] 有望なニッチが見つかりませんでした。条件を変えて再試行します...")
            time.sleep(10)
            continue
            
        print(f"[System] {len(strategies)} 件の有望な戦略（Strategy）を獲得しました。製造を開始します。")
        
        # 2. 獲得した戦略を順次実行
        for strat in strategies:
            # 言語はランダム、あるいは戦略に応じて固定も可能
            lang = random.choice(TARGET_LANGUAGES)
            
            success = orchestrator.execute_pipeline(strategy_data=strat, language=lang)
            
            if success:
                # ★ 記事の生成に成功したら、即座に世界へ公開する
                publisher.publish_to_world(commit_message=f"Auto-generate: {strat['target_keyword']} ({lang})")
                
                wait_time = random.randint(30, 60)
                print(f"[System] 次の製造まで {wait_time} 秒待機中...")
                time.sleep(wait_time)
            
        print("[System] サイクル完了。市場データの更新を待ちます...")
        time.sleep(120) # 次の市場調査まで少し待つ
        iteration += 1

if __name__ == "__main__":
    main()