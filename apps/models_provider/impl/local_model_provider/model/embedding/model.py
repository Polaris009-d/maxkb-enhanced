# coding=utf-8
"""
    @project: MaxKB
    @Author：虎虎
    @file： model.py
    @date：2025/11/5 15:26
    @desc:
"""
import os
from typing import Dict

from langchain_huggingface import HuggingFaceEmbeddings

from common.utils.logger import maxkb_logger
from models_provider.base_model_provider import MaxKBBaseModel

max_retries = 3


class LocalEmbedding(MaxKBBaseModel, HuggingFaceEmbeddings):
    @staticmethod
    def is_cache_model():
        return True

    @staticmethod
    def new_instance(model_type, model_name, model_credential: Dict[str, object], **model_kwargs):
        for attempt in range(max_retries):
            try:
                # Use local_files_only=True to prevent HuggingFace from trying to connect to the network.
                # When cache_folder is set, resolve the full local model path to bypass HF Hub cache lookup.
                cache_dir = model_credential.get('cache_folder')
                if cache_dir:
                    model_path = os.path.join(cache_dir, model_name.replace('/', '_'))
                    if not os.path.exists(model_path):
                        model_path = model_name  # Fallback to original name
                else:
                    model_path = model_name
                embedding = LocalEmbedding(model_name=model_path, cache_folder=cache_dir,
                                           model_kwargs={'device': model_credential.get('device'), 'local_files_only': True},
                                           encode_kwargs={'normalize_embeddings': True}
                                           )
                # 测试一下是否真的能用
                embedding.embed_query("test")
                return embedding
            except Exception as e:
                if 'meta tensor' in str(e).lower() and attempt < max_retries - 1:
                    maxkb_logger.warning(
                        f"Test failed with meta tensor error, retrying... (attempt {attempt + 1}/{max_retries})")
                    import time
                    time.sleep(1)
                    continue
                raise e
