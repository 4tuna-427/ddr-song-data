import os
import json
import requests

# GAS の Web API URL (または GitHub Secrets から取得)
GAS_API_URL = os.environ.get("GAS_API_URL")

def main():
    if not GAS_API_URL:
        raise ValueError("環境変数 GAS_API_URL が設定されていません。")

    print(f"Fetching master data from GAS...")
    response = requests.get(GAS_API_URL, allow_redirects=True, timeout=30)
    response.raise_for_status()

    data = response.json()
    print(f"Successfully fetched {len(data)} items.")

    # 出力先ディレクトリ (dist/) の作成
    output_dir = "dist"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "songs.json")

    # 整形して保存
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Saved master data to {output_path}")

if __name__ == "__main__":
    main()
