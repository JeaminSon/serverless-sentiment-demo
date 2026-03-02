from transformers import AutoTokenizer, AutoModelForSequenceClassification

MODEL_ID = "daekeun-ml/koelectra-small-v3-nsmc"
OUT_DIR = "/opt/model"

AutoTokenizer.from_pretrained(MODEL_ID).save_pretrained(OUT_DIR)
AutoModelForSequenceClassification.from_pretrained(MODEL_ID).save_pretrained(OUT_DIR)

print("Saved model to", OUT_DIR)