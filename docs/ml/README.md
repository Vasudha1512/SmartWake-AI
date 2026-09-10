# SmartWake AI — Machine Learning Subsystem Documentation

This directory contains the comprehensive technical specifications, training strategies, fallback policies, and runtime integration architecture for the SmartWake AI Machine Learning subsystem (Phase 3).

---

## Documentation Index by Phase

| Phase | Title | Document Link | Focus & Highlights |
| :---: | :--- | :--- | :--- |
| **3.0** | ML Feature Engineering | [feature_engineering.md](file:///c:/Users/ADMIN/OneDrive/Documents/Wakeup%20AI/docs/ml/feature_engineering.md) | 30 canonical pre-challenge features, point-in-time extraction, leakage prevention. |
| **3.1** | ML Training Strategy | [ml_training_strategy.md](file:///c:/Users/ADMIN/OneDrive/Documents/Wakeup%20AI/docs/ml/ml_training_strategy.md) | Objective-performance target derivation, chronological splitting, data leakage boundaries. |
| **3.2** | Baseline ML Model Training | [baseline_model_training.md](file:///c:/Users/ADMIN/OneDrive/Documents/Wakeup%20AI/docs/ml/baseline_model_training.md) | Scikit-Learn Logistic Regression pipeline, ColumnTransformer, artifact serialization (`joblib`). |
| **3.3 & 3.4** | Adaptive Decision Engine | [adaptive_decision_engine.md](file:///c:/Users/ADMIN/OneDrive/Documents/Wakeup%20AI/docs/ml/adaptive_decision_engine.md) | Runtime decision boundary, user sovereignty over challenge type, fixed preference bypass. |
| **3.5** | Cold-Start & Fallback Strategy | [cold_start_and_fallback.md](file:///c:/Users/ADMIN/OneDrive/Documents/Wakeup%20AI/docs/ml/cold_start_and_fallback.md) | 7-level fallback hierarchy, 10 failure modes, zero telemetry fabrication. |
| **3.6** | ML Evaluation & Runtime Integration | [ml_evaluation_and_runtime_integration.md](file:///c:/Users/ADMIN/OneDrive/Documents/Wakeup%20AI/docs/ml/ml_evaluation_and_runtime_integration.md) | Dynamic multi-class metrics, fair heuristic comparison, offline-runtime parity, sovereignty audit. |

---

## Core System Invariants

1. **4-Tier Target Separation**: Explicit distinction between *heuristic-derived baseline target*, *ML prediction*, *runtime personalization*, and *actual future user outcomes*.
2. **User Sovereignty**: User-selected challenge type (`dance`, `math`, `memory`, `tongue_twister`, `push_ups`) is strictly immutable. ML never selects, alters, or overrides it.
3. **Fail-Safe Operation**: Under no circumstances does an alarm fail to trigger or fail to present a challenge due to ML exceptions or missing historical telemetry.
4. **Zero Synthetic Telemetry at Runtime**: Runtime execution strictly consumes authentic SQLite database records.
