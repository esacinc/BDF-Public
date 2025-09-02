# utils/prepare_cache.py

from sentence_transformers import SentenceTransformer
import os
import shutil
import torch

MODEL_NAME = "sentence-transformers/all-mpnet-base-v2"
TARGET_PATH = "/root/.cache/bdikit/models/magneto-gdc-v0.1"  # Must match what BDI expects

print(f"📥 Downloading model: {MODEL_NAME}")
model = SentenceTransformer(MODEL_NAME)

# Ensure parent directory exists
parent_dir = os.path.dirname(TARGET_PATH)
os.makedirs(parent_dir, exist_ok=True)

# Remove existing path (file or directory or symlink)
if os.path.exists(TARGET_PATH) or os.path.islink(TARGET_PATH):
    print(f"🧹 Removing existing path at: {TARGET_PATH}")
    try:
        if os.path.isdir(TARGET_PATH):
            shutil.rmtree(TARGET_PATH)
        else:
            os.unlink(TARGET_PATH)
    except Exception as e:
        print(f"⚠️ Failed to remove {TARGET_PATH}: {e}")
        exit(1)

# Save only the model weights as a binary file
print(f"💾 Saving state_dict to: {TARGET_PATH}")
torch.save(model.state_dict(), TARGET_PATH)
print("✅ Model state_dict saved successfully.")
