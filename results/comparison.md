Golden set: 20 reviewed cards. Quality columns are measured on the golden documents of each run; valid rate, latency and cost on all its documents.

| run | model | mode | prompt | sampling | docs | valid | facts | halluc. | omitted | class. | content F1 | overall | p50 s | p95 s | $/1000 docs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| haiku_text_v3_medium | haiku | text | v3 | effort=medium | 20 | 1.00 | 0.91 | 0.03 | 0.07 | 0.77 | 0.71 | 0.80 | 3.8 | 8.0 | 0.96 |
| haiku_image_v3_medium | haiku | image | v3 | effort=medium | 20 | 1.00 | 0.94 | 0.07 | 0.03 | 1.00 | 0.83 | 0.93 | 6.1 | 12.4 | 2.13 |
| haiku_text-image_v3_medium | haiku | text+image | v3 | effort=medium | 20 | 1.00 | 0.96 | 0.09 | 0.02 | 0.97 | 0.82 | 0.92 | 5.7 | 9.2 | 2.55 |
| haiku_pdf_v3_medium | haiku | pdf | v3 | effort=medium | 20 | 1.00 | 0.97 | 0.09 | 0.00 | 1.00 | 0.83 | 0.93 | 5.2 | 9.3 | 2.78 |
| haiku_image_v1_medium | haiku | image | v1 | effort=medium | 20 | 1.00 | 0.91 | 0.07 | 0.05 | 0.82 | 0.68 | 0.81 | 5.3 | 10.0 | 1.94 |
| haiku_image_v2_medium | haiku | image | v2 | effort=medium | 20 | 1.00 | 0.94 | 0.05 | 0.06 | 1.00 | 0.82 | 0.92 | 5.7 | 11.5 | 2.15 |
| haiku_image_v3_low | haiku | image | v3 | effort=low | 20 | 1.00 | 0.89 | 0.16 | 0.04 | 0.90 | 0.79 | 0.86 | 3.6 | 6.6 | 1.87 |
| haiku_image_v3_high | haiku | image | v3 | effort=high | 20 | 1.00 | 0.97 | 0.05 | 0.00 | 0.97 | 0.86 | 0.94 | 8.4 | 18.7 | 2.47 |
| haiku_image_v3_medium_tier50 | haiku | image | v3 | effort=medium | 50 | 1.00 | 0.94 | 0.05 | 0.03 | 1.00 | 0.84 | 0.93 | 6.9 | 10.6 | 1.98 |
| sonnet_text_v3_medium | sonnet | text | v3 | effort=medium | 20 | 1.00 | 0.91 | 0.10 | 0.05 | 0.93 | 0.76 | 0.86 | 2.8 | 3.8 | 16.59 |
| sonnet_image_v3_medium | sonnet | image | v3 | effort=medium | 20 | 1.00 | 0.95 | 0.09 | 0.00 | 1.00 | 0.87 | 0.94 | 5.5 | 9.7 | 35.10 |
| sonnet_text-image_v3_medium | sonnet | text+image | v3 | effort=medium | 20 | 1.00 | 0.94 | 0.09 | 0.00 | 0.97 | 0.85 | 0.92 | 4.9 | 9.3 | 46.18 |
| sonnet_pdf_v3_medium | sonnet | pdf | v3 | effort=medium | 20 | 1.00 | 0.96 | 0.09 | 0.00 | 1.00 | 0.88 | 0.95 | 4.7 | 9.2 | 49.58 |
| gpt6luna_text_v3 | gpt-6-luna | text | v3 | default | 20 | 1.00 | 0.93 | 0.07 | 0.05 | 0.80 | 0.71 | 0.81 | 7.4 | 11.5 | 0.80 |
| gpt6luna_image_v3 | gpt-6-luna | image | v3 | default | 20 | 1.00 | 0.95 | 0.10 | 0.00 | 1.00 | 0.82 | 0.92 | 10.5 | 22.7 | 1.87 |
| gpt6luna_text-image_v3 | gpt-6-luna | text+image | v3 | default | 20 | 1.00 | 0.94 | 0.12 | 0.00 | 1.00 | 0.83 | 0.92 | 12.4 | 25.6 | 2.28 |
| gpt6luna_image_v3_t0 | gpt-6-luna | image | v3 | t=0.0 | 20 | 1.00 | 0.94 | 0.12 | 0.00 | 0.97 | 0.82 | 0.91 | 10.9 | 22.7 | 1.87 |
| gpt6luna_image_v3_t07_p09 | gpt-6-luna | image | v3 | t=0.7, top_p=0.9 | 20 | 1.00 | 0.95 | 0.10 | 0.00 | 1.00 | 0.82 | 0.92 | 10.7 | 21.9 | 0.61 |
| qwen8b_text_v1_t0 | qwen3-vl-8b | text | v1 | t=0.0 | 20 | 1.00 | 0.76 | 0.28 | 0.09 | 0.40 | 0.43 | 0.53 | 3.8 | 15.5 | 0.00 |
| qwen8b_image_v1_t0 | qwen3-vl-8b | image | v1 | t=0.0 | 20 | 1.00 | 0.79 | 0.34 | 0.05 | 0.47 | 0.47 | 0.58 | 9.3 | 35.0 | 0.00 |
| qwen8b_text-image_v1_t0 | qwen3-vl-8b | text+image | v1 | t=0.0 | 20 | 0.95 | 0.73 | 0.41 | 0.03 | 0.43 | 0.46 | 0.54 | 10.1 | 48.8 | 0.00 |
| qwen8b_text_v2_t0 | qwen3-vl-8b | text | v2 | t=0.0 | 20 | 1.00 | 0.78 | 0.21 | 0.16 | 0.73 | 0.65 | 0.72 | 3.1 | 13.2 | 0.00 |
| qwen8b_image_v2_t0 | qwen3-vl-8b | image | v2 | t=0.0 | 20 | 1.00 | 0.80 | 0.28 | 0.12 | 0.82 | 0.73 | 0.78 | 8.9 | 35.3 | 0.00 |
| qwen8b_text-image_v2_t0 | qwen3-vl-8b | text+image | v2 | t=0.0 | 20 | 1.00 | 0.81 | 0.26 | 0.10 | 0.78 | 0.74 | 0.78 | 10.0 | 37.2 | 0.00 |
| qwen8b_image_v2_t07 | qwen3-vl-8b | image | v2 | t=0.7 | 20 | 1.00 | 0.82 | 0.22 | 0.11 | 0.80 | 0.70 | 0.77 | 8.7 | 40.9 | 0.00 |
| qwen4b_text_v2_t0 | qwen3-vl-4b | text | v2 | t=0.0 | 20 | 1.00 | 0.80 | 0.21 | 0.13 | 0.60 | 0.55 | 0.65 | 2.2 | 17.7 | 0.00 |
| qwen4b_image_v2_t0 | qwen3-vl-4b | image | v2 | t=0.0 | 20 | 1.00 | 0.82 | 0.24 | 0.08 | 0.80 | 0.66 | 0.76 | 5.2 | 23.4 | 0.00 |
| qwen4b_text-image_v2_t0 | qwen3-vl-4b | text+image | v2 | t=0.0 | 20 | 1.00 | 0.80 | 0.28 | 0.09 | 0.72 | 0.61 | 0.71 | 5.6 | 36.6 | 0.00 |
| qwen8b_image_v3_t0 | qwen3-vl-8b | image | v3 | t=0.0 | 20 | 1.00 | 0.79 | 0.34 | 0.08 | 0.80 | 0.69 | 0.76 | 7.5 | 34.4 | 0.00 |
| qwen8b_text_v3_t0 | qwen3-vl-8b | text | v3 | t=0.0 | 20 | 1.00 | 0.79 | 0.26 | 0.11 | 0.70 | 0.63 | 0.71 | 2.4 | 11.3 | 0.00 |
| qwen8b_image_v3_t07_p09 | qwen3-vl-8b | image | v3 | t=0.7, top_p=0.9 | 20 | 1.00 | 0.79 | 0.33 | 0.09 | 0.80 | 0.69 | 0.76 | 7.3 | 30.6 | 0.00 |
| qwen4b_image_v3_t0 | qwen3-vl-4b | image | v3 | t=0.0 | 20 | 1.00 | 0.79 | 0.31 | 0.09 | 0.70 | 0.65 | 0.71 | 3.9 | 28.4 | 0.00 |

Overall score by stratum:

| run | en-notes | en-scan | en-slides | uk |
|---|---|---|---|---|
| haiku_text_v3_medium | 0.83 | 0.57 | 0.90 | 0.81 |
| haiku_image_v3_medium | 0.93 | 0.92 | 0.94 | 0.91 |
| haiku_text-image_v3_medium | 0.92 | 0.88 | 0.92 | 0.93 |
| haiku_pdf_v3_medium | 0.94 | 0.91 | 0.89 | 0.95 |
| haiku_image_v1_medium | 0.88 | 0.86 | 0.82 | 0.67 |
| haiku_image_v2_medium | 0.93 | 0.87 | 0.93 | 0.92 |
| haiku_image_v3_low | 0.87 | 0.80 | 0.78 | 0.91 |
| haiku_image_v3_high | 0.94 | 0.93 | 0.89 | 0.95 |
| haiku_image_v3_medium_tier50 | 0.94 | 0.91 | 0.94 | 0.92 |
| sonnet_text_v3_medium | 0.93 | 0.59 | 0.87 | 0.91 |
| sonnet_image_v3_medium | 0.94 | 0.91 | 0.95 | 0.96 |
| sonnet_text-image_v3_medium | 0.92 | 0.89 | 0.91 | 0.96 |
| sonnet_pdf_v3_medium | 0.95 | 0.92 | 0.94 | 0.96 |
| gpt6luna_text_v3 | 0.82 | 0.59 | 0.88 | 0.88 |
| gpt6luna_image_v3 | 0.93 | 0.90 | 0.88 | 0.94 |
| gpt6luna_text-image_v3 | 0.94 | 0.84 | 0.92 | 0.94 |
| gpt6luna_image_v3_t0 | 0.91 | 0.87 | 0.92 | 0.93 |
| gpt6luna_image_v3_t07_p09 | 0.92 | 0.89 | 0.93 | 0.94 |
| qwen8b_text_v1_t0 | 0.63 | 0.45 | 0.49 | 0.46 |
| qwen8b_image_v1_t0 | 0.65 | 0.68 | 0.55 | 0.44 |
| qwen8b_text-image_v1_t0 | 0.64 | 0.43 | 0.54 | 0.46 |
| qwen8b_text_v2_t0 | 0.79 | 0.48 | 0.69 | 0.76 |
| qwen8b_image_v2_t0 | 0.84 | 0.73 | 0.80 | 0.72 |
| qwen8b_text-image_v2_t0 | 0.84 | 0.72 | 0.75 | 0.74 |
| qwen8b_image_v2_t07 | 0.84 | 0.71 | 0.83 | 0.69 |
| qwen4b_text_v2_t0 | 0.75 | 0.50 | 0.59 | 0.63 |
| qwen4b_image_v2_t0 | 0.83 | 0.67 | 0.72 | 0.73 |
| qwen4b_text-image_v2_t0 | 0.76 | 0.65 | 0.74 | 0.66 |
| qwen8b_image_v3_t0 | 0.83 | 0.74 | 0.72 | 0.70 |
| qwen8b_text_v3_t0 | 0.76 | 0.53 | 0.64 | 0.75 |
| qwen8b_image_v3_t07_p09 | 0.83 | 0.76 | 0.67 | 0.72 |
| qwen4b_image_v3_t0 | 0.80 | 0.67 | 0.61 | 0.67 |

Per-field score (facts and classification: accuracy; content lists: F1):

| run | course_title | course_code | institution | lecturers | lecture_number | lecture_title | year | term | discipline | doc_type | topics | key_terms | references |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| haiku_text_v3_medium | 0.95 | 0.80 | 0.95 | 0.95 | 0.90 | 0.90 | 0.90 | 0.90 | 0.85 | 0.70 | 0.62 | 0.59 | 0.90 |
| haiku_image_v3_medium | 0.90 | 0.95 | 0.95 | 1.00 | 0.90 | 0.85 | 1.00 | 1.00 | 1.00 | 1.00 | 0.79 | 0.71 | 1.00 |
| haiku_text-image_v3_medium | 0.95 | 1.00 | 0.90 | 1.00 | 0.90 | 0.90 | 1.00 | 1.00 | 0.95 | 1.00 | 0.77 | 0.74 | 0.95 |
| haiku_pdf_v3_medium | 0.95 | 1.00 | 0.95 | 1.00 | 0.95 | 0.90 | 1.00 | 1.00 | 1.00 | 1.00 | 0.77 | 0.76 | 0.95 |
| haiku_image_v1_medium | 0.95 | 0.80 | 0.95 | 0.95 | 0.75 | 0.95 | 1.00 | 0.95 | 0.85 | 0.80 | 0.80 | 0.72 | 0.52 |
| haiku_image_v2_medium | 0.95 | 1.00 | 0.95 | 1.00 | 0.80 | 0.90 | 1.00 | 0.95 | 1.00 | 1.00 | 0.79 | 0.73 | 0.94 |
| haiku_image_v3_low | 0.90 | 0.85 | 1.00 | 0.90 | 0.75 | 0.80 | 0.95 | 0.95 | 0.90 | 0.90 | 0.75 | 0.71 | 0.90 |
| haiku_image_v3_high | 0.95 | 0.95 | 0.95 | 1.00 | 0.95 | 1.00 | 1.00 | 1.00 | 0.95 | 1.00 | 0.83 | 0.75 | 1.00 |
| haiku_image_v3_medium_tier50 | 0.95 | 0.90 | 0.95 | 1.00 | 0.90 | 0.85 | 1.00 | 1.00 | 1.00 | 1.00 | 0.82 | 0.73 | 0.99 |
| sonnet_text_v3_medium | 1.00 | 0.85 | 0.90 | 0.95 | 0.85 | 0.85 | 0.90 | 0.95 | 0.95 | 0.90 | 0.69 | 0.65 | 0.95 |
| sonnet_image_v3_medium | 1.00 | 0.85 | 0.95 | 1.00 | 0.95 | 0.90 | 1.00 | 0.95 | 1.00 | 1.00 | 0.86 | 0.77 | 0.99 |
| sonnet_text-image_v3_medium | 1.00 | 0.85 | 0.95 | 1.00 | 0.95 | 0.90 | 0.95 | 0.95 | 0.95 | 1.00 | 0.83 | 0.78 | 0.95 |
| sonnet_pdf_v3_medium | 0.95 | 0.95 | 0.95 | 1.00 | 0.95 | 0.90 | 1.00 | 1.00 | 1.00 | 1.00 | 0.83 | 0.80 | 1.00 |
| gpt6luna_text_v3 | 1.00 | 0.90 | 0.90 | 1.00 | 0.85 | 0.90 | 0.90 | 0.95 | 0.90 | 0.70 | 0.56 | 0.60 | 0.95 |
| gpt6luna_image_v3 | 0.95 | 0.95 | 0.95 | 0.95 | 0.95 | 0.85 | 1.00 | 1.00 | 1.00 | 1.00 | 0.78 | 0.72 | 0.95 |
| gpt6luna_text-image_v3 | 0.95 | 0.95 | 0.90 | 1.00 | 0.95 | 0.85 | 0.95 | 0.95 | 1.00 | 1.00 | 0.72 | 0.76 | 1.00 |
| gpt6luna_image_v3_t0 | 0.95 | 0.95 | 0.95 | 0.95 | 0.90 | 0.85 | 1.00 | 1.00 | 0.95 | 1.00 | 0.76 | 0.71 | 1.00 |
| gpt6luna_image_v3_t07_p09 | 0.95 | 0.95 | 0.95 | 0.95 | 0.95 | 0.85 | 1.00 | 1.00 | 1.00 | 1.00 | 0.73 | 0.73 | 1.00 |
| qwen8b_text_v1_t0 | 0.75 | 0.55 | 0.95 | 0.85 | 0.65 | 0.80 | 0.90 | 0.65 | 0.35 | 0.45 | 0.55 | 0.50 | 0.23 |
| qwen8b_image_v1_t0 | 0.80 | 0.55 | 0.95 | 0.90 | 0.75 | 0.75 | 0.95 | 0.65 | 0.50 | 0.45 | 0.64 | 0.55 | 0.20 |
| qwen8b_text-image_v1_t0 | 0.75 | 0.35 | 0.90 | 0.95 | 0.75 | 0.75 | 0.90 | 0.50 | 0.45 | 0.40 | 0.68 | 0.50 | 0.20 |
| qwen8b_text_v2_t0 | 0.85 | 0.70 | 0.70 | 0.95 | 0.60 | 0.65 | 0.90 | 0.90 | 0.80 | 0.65 | 0.54 | 0.52 | 0.90 |
| qwen8b_image_v2_t0 | 0.75 | 0.80 | 0.70 | 1.00 | 0.60 | 0.80 | 0.90 | 0.85 | 0.85 | 0.80 | 0.68 | 0.59 | 0.90 |
| qwen8b_text-image_v2_t0 | 0.75 | 0.80 | 0.70 | 0.95 | 0.65 | 0.85 | 0.95 | 0.85 | 0.75 | 0.80 | 0.72 | 0.61 | 0.90 |
| qwen8b_image_v2_t07 | 0.80 | 0.80 | 0.75 | 1.00 | 0.60 | 0.85 | 0.95 | 0.85 | 0.80 | 0.80 | 0.65 | 0.55 | 0.90 |
| qwen4b_text_v2_t0 | 0.85 | 0.55 | 0.75 | 1.00 | 0.55 | 0.80 | 0.90 | 1.00 | 0.55 | 0.65 | 0.48 | 0.48 | 0.70 |
| qwen4b_image_v2_t0 | 0.75 | 0.70 | 0.70 | 1.00 | 0.55 | 0.95 | 0.95 | 0.95 | 0.75 | 0.85 | 0.67 | 0.51 | 0.80 |
| qwen4b_text-image_v2_t0 | 0.80 | 0.60 | 0.70 | 1.00 | 0.50 | 0.85 | 0.95 | 1.00 | 0.75 | 0.70 | 0.60 | 0.48 | 0.75 |
| qwen8b_image_v3_t0 | 0.75 | 0.80 | 0.70 | 0.95 | 0.70 | 0.75 | 0.90 | 0.80 | 0.90 | 0.70 | 0.66 | 0.59 | 0.81 |
| qwen8b_text_v3_t0 | 0.85 | 0.75 | 0.70 | 0.95 | 0.55 | 0.75 | 0.90 | 0.85 | 0.75 | 0.65 | 0.54 | 0.50 | 0.85 |
| qwen8b_image_v3_t07_p09 | 0.70 | 0.75 | 0.75 | 0.95 | 0.70 | 0.75 | 0.90 | 0.80 | 0.90 | 0.70 | 0.61 | 0.60 | 0.87 |
| qwen4b_image_v3_t0 | 0.70 | 0.65 | 0.75 | 0.95 | 0.55 | 0.80 | 0.95 | 0.95 | 0.75 | 0.65 | 0.65 | 0.48 | 0.81 |
