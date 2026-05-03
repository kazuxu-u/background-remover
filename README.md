# 背景透過アプリ

写真をアップロードして、アルファチャンネル付きPNGとして保存するローカルWebアプリです。
ComfyUI の `RMBG` ノードを使って、写真をアルファチャンネル付きPNGとして保存するローカルWebアプリです。
ComfyUI は `http://127.0.0.1:8188` で起動している必要があります。

## 起動

```powershell
cd "C:\Users\momop\OneDrive\ドキュメント\GPT雑用\background-remover-app"
python server.py
```

ブラウザで `http://127.0.0.1:8787` を開きます。

この環境では `vendor` フォルダに背景透過ライブラリを入れてあるため、そのまま起動できます。
別の環境で使う場合は次を実行してください。

```powershell
python -m pip install --target vendor -r requirements.txt
```

## 出力

処理直後の透過PNGは `outputs` フォルダに保存されます。
画面の「保存」ボタンを押すと `C:\Users\momop\OneDrive\画像\切り抜き` にコピーされます。

## GPU設定

既定値は `REMBG_PROVIDER=cpu` です。GPUを試す場合:

```powershell
$env:REMBG_PROVIDER="directml"
python server.py
```
