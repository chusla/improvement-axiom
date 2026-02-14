# Contributing

## Getting Started

1. Fork and clone the repository
2. Create a virtual environment: `python -m venv venv`
3. Activate it: `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (Unix)
4. Install in dev mode: `pip install -e ".[dev]"`
5. Run tests: `pytest`

## Development Workflow

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Make your changes
3. Add or update tests in `tests/`
4. Run `pytest` and `ruff check src/`
5. Commit with a clear message
6. Open a pull request

## Code Style

- Line length: 100 characters
- Linting: `ruff check src/`
- Follow existing patterns in the codebase

## Reporting Issues

Use GitHub Issues. Include:
- Description of the problem
- Steps to reproduce
- Expected vs. actual behavior
- Python version and OS
