# Resonance MIDI Player

「ブループロトコル：スターレゾナンス」の楽器演奏向けに、Standard MIDI File（MIDI）の音符をWindowsのキーボード入力へ変換するデスクトップツールです。

ゲームプロセスやメモリの読み書きは行わず、Windowsの通常のキー入力APIを使用します。

## 主な機能

- SMF format 0 / 1の`.mid`・`.midi`ファイルを読み込み
- 再生・停止・先頭へ戻る・シーク
- 再生速度、移調、キー保持時間、開始カウントダウンの設定
- MIDI channel 10のドラム除外
- C3～B6の4オクターブ演奏
- `>` / `<`によるゲーム側の音域表示の自動切り替え
- 対象ゲームウィンドウの自動再取得とフォーカス
- 常に手前、背景透明度、ウィンドウ位置の保存

## ダウンロード

GitHubのReleasesから最新版のZIPをダウンロードし、展開後に`ResonanceMidiPlayer.exe`を実行してください。

デジタル署名のない個人制作アプリのため、Windows SmartScreenが警告を表示する場合があります。

## 基本的な使い方

1. ゲームでピアノの演奏画面を開きます。
2. `+ MIDI`から演奏するMIDIファイルを選択します。
3. 対象欄で「ブループロトコル：スターレゾナンス」を選択します。
4. 再生ボタンを押します。

ゲーム側の鍵盤初期位置は`Z = C3`を前提としています。4オクターブ自動切り替えを有効にすると、C6～B6の発音時に`>`で高音側へ移動し、発音後に`<`で戻ります。

初期設定は次のとおりです。

- 再生速度：1.0
- 移調：0半音
- キー保持：1ms
- 音域切替待機：20ms
- ドラム除外：オン
- 4オクターブ自動切替：オン
- 開始カウントダウン：3秒
- 常に手前：オン
- 背景透明度：50%

設定は`%APPDATA%\ResonanceMidiPlayer\config.json`に保存されます。リポジトリや配布ZIPにユーザー設定は含まれません。

## ソースから実行

WindowsとPython 3.11以降を使用してください。

```powershell
python -m pip install -r requirements.txt
python qt_app.py
```

## EXEをビルド

PyInstallerをインストールしてから実行します。

```powershell
python -m pip install pyinstaller
.\build.ps1
```

完成物は`dist\ResonanceMidiPlayer.exe`です。

## テスト

```powershell
python -m unittest discover -s tests -v
```

## 注意

自動入力ツールの利用可否は、ゲームの利用規約や運営方針を確認してください。本ツールの利用は自己責任です。ゲームを管理者権限で起動している場合は、入力を届けるため本ツールも同じ権限で起動する必要があります。

MIDIファイルは同梱していません。利用するMIDIの著作権・利用条件は各自で確認してください。
