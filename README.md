# SmartWake AI

SmartWake AI is an intelligent, personalized alarm system designed to make users actually wake up and complete a required task before the alarm can be dismissed.

The system uses AI/ML to learn from the user's previous snooze behavior, wake-up behavior, task completion time, successes, and failures. Based on this history, it adaptively selects an appropriate wake-up challenge and difficulty.

Current challenge types include:
- Dance
- Math
- Memory
- Tongue Twister
- Push-ups

Generative AI can be used to create personalized daily challenges, while AI/computer vision can optionally verify physical or object-based tasks.

The project is being developed as a web application using React and FastAPI, with Python-based machine learning. A mobile application is planned as a future extension.

## Architecture Phases
- **Phase 1:** Core Data Models, Database Schemas & Session Management
- **Phase 2:** Alarm Scheduling, Challenge Catalog & Verification Engine
- **Phase 3:** Machine Learning Adaptive Intelligence (Feature Engineering, Baseline Classifier, Personalization Engine, Adaptive Decision Engine)
- **Phase 4:** Generative AI Architecture & Challenge Generation (Foundation, Provider Abstraction, Multi-Category Synthesis, Fallback)
  - See [docs/architecture/genai_architecture.md](docs/architecture/genai_architecture.md) for Phase 4 GenAI architecture specifications.