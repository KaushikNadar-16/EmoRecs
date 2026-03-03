@echo off
cd /d "D:\Project Materials\Emotion"
python -u train_emotion_model.py > train_log.txt 2>&1
echo DONE >> train_log.txt
