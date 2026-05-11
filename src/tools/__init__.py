"""Mock tool registry: maps tool names to their callables."""

from src.tools.escalate_to_human import escalate_to_human
from src.tools.grant_file_access import grant_file_access
from src.tools.lookup_employee import lookup_employee
from src.tools.query_hr_database import query_hr_database
from src.tools.reset_password import reset_password

TOOL_REGISTRY: dict = {
    "reset_password": reset_password,
    "lookup_employee": lookup_employee,
    "grant_file_access": grant_file_access,
    "query_hr_database": query_hr_database,
    "escalate_to_human": escalate_to_human,
}
