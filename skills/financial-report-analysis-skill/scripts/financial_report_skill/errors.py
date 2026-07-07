from __future__ import annotations

class SkillError(Exception):
    """Base exception for this skill."""
    code = "E_SKILL_ERROR"

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

class SkillEnvironmentError(SkillError):
    code = "E_ENVIRONMENT_UNSUPPORTED"

class SkillInputError(SkillError):
    code = "E_INPUT_INVALID"

class SkillValidationError(SkillError):
    code = "E_VALIDATION_FAILED"

class WindFinancialStatementValidationError(SkillValidationError):
    code = "E_WIND_VALIDATION_FAILED"

class SkillRuntimeError(SkillError):
    code = "E_RUNTIME_FAILED"
