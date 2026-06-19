# -*- coding: utf-8 -*-
"""Izračunava sve metrike za zadate lekcije preko Flask endpointa (puni validation_cache).
Pokreni: venv/Scripts/python.exe -m eval.compute_lessons 2 3
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app import app  # noqa: E402

METRICS = ['lint', 'readability', 'ambiguity', 'grammar-homogeneity', 'face-validity',
           'solo-judge', 'ioc', 'misconception-mining', 'stem-only-solvability', 'cove',
           'solvability']


def main():
    lessons = [int(x) for x in sys.argv[1:]] or [2, 3]
    client = app.test_client()
    for lid in lessons:
        for m in METRICS:
            url = f'/api/lessons/{lid}/{m}'
            print(f'[compute] lesson {lid} -> {m} ...', flush=True)
            r = client.get(url, headers={'X-LLM-Provider': 'anthropic'})
            print(f'         status {r.status_code}', flush=True)
    print('[compute] done.')


if __name__ == '__main__':
    main()
