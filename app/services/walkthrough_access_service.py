"""Fixed-feature walkthrough access engine. Fail-closed for unknown mappings."""
from __future__ import annotations
import csv
import re
from pathlib import Path
from dataclasses import dataclass
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parent
FILES = {
    'steps': 'Danube One App Walkthrough(1).xlsx',
    'features': 'Feature Mapping.xlsx',
    'roles': 'Role Mapping.xlsx',
    'mobile_app': 'Danube One - Feature Mapping Table(B2B - Mobile App).xlsx',
    'web_app': 'Danube One - Feature Mapping Table(B2B - Web Portal).csv',
}
TEAM_COL = {'indirect': {'HOS': 9, 'DOS': 10, 'RM': 11}, 'direct': {'HOS': 12, 'DOS': 13, 'RM': 14}}
COMMON_COL = {'FREELANCER': 3, 'AGENCY_ADMIN': 4, 'AGENT': 5, 'MANAGEMENT': 6, 'CXO': 7, 'HOD': 8, 'BDCXO': 15, 'BDHOD': 16, 'BDTL': 17, 'BDE': 18, 'REFERRAL_TEAM_R3': 19, 'REFERRAL_TEAM_R1': 20, 'REFERRAL_TEAM_MEMBER': 21, 'REFERRAL_ASSOCIATE': 22, 'MTH': 23, 'MTE': 24}
# 0-indexed columns. PARTNER_OWNER deliberately absent: no mapping in source.

def norm(value):
    return re.sub(r'\s+', ' ', str(value or '').replace('\xa0', ' ')).strip().casefold()

def rows_xlsx(path):
    book = load_workbook(path, read_only=True, data_only=True)
    return [list(r) for r in book.active.values]

def rows_csv(path):
    with open(path, encoding='cp1252', newline='') as stream:
        return list(csv.reader(stream))

def cell(row, col):
    return row[col] if col < len(row) else None

@dataclass(frozen=True)
class Guide:
    name: str
    steps: str
    key: str

class WalkthroughEngine:
    def __init__(self, directory=ROOT):
        directory = Path(directory)
        self.guides = {}
        for row in rows_xlsx(directory / FILES['steps'])[1:]:
            name = norm(cell(row, 1))
            if not name or not norm(cell(row, 2)) or name.startswith('based on the login'):
                continue
            if name in self.guides:
                raise ValueError(f'Duplicate guide {name}')
            self.guides[name] = Guide(str(row[1]).strip(), str(row[2]).strip(), norm(cell(row, 3)))
        self.mapping = {}
        for row in rows_xlsx(directory / FILES['features'])[2:]:
            name = norm(cell(row, 0))
            if name in self.guides:
                self.mapping[name] = {'web_app': (norm(cell(row, 1)), norm(cell(row, 2))), 'mobile_app': (norm(cell(row, 3)), norm(cell(row, 4)))}
        self.tables = {
            'mobile_app': rows_xlsx(directory / FILES['mobile_app']),
            'web_app': rows_csv(directory / FILES['web_app']),
        }
        self.frontend_roles = {norm(row[1]): str(row[0]).strip() for row in rows_xlsx(directory / FILES['roles'])[1:] if row[0] and row[1]}
        self.approved_roles = set(self.frontend_roles.values())
        self.issues = self.validate()


    def validate(self):
        issues = []

        for name, guide in self.guides.items():
            if name not in self.mapping:
                issues.append(
                    f"Missing feature mapping: {guide.name}"
                )
                continue

            for source in self.tables:
                label, key = self.mapping[name][source]

                # Explicitly public features are valid.
                if label == "public" and not key:
                    continue

                if label == "public" and key:
                    issues.append(
                        f"Invalid PUBLIC mapping: "
                        f"{guide.name} ({source})"
                    )
                    continue

                if not label and not key:
                    issues.append(
                        f"No mapping: {guide.name} ({source})"
                    )

        return issues

    def permission(self, name, role, source, employee_type):
        """Return (allowed, reason); never accept unknown roles or ambiguous matches."""
        name = norm(name)
        if (
            source not in self.tables
            or employee_type not in ("direct", "indirect", "")
        ):
            return False, "invalid_context"

        if name not in self.guides or name not in self.mapping:
            return False, "unknown_feature"

        label, key = self.mapping[name][source]

        if label == "public" and not key:
            return True, "public_feature"

        role = self.frontend_roles.get(norm(role))

        if role not in self.approved_roles:
            return False, "unknown_role"

        if role in ("HOS", "DOS", "RM"):
            col = TEAM_COL.get(employee_type, {}).get(role)
        else:
            col = COMMON_COL.get(role)

        if col is None or (
            source == "web_app" and col >= 23
        ):
            return False, "unmapped_role"

        if not label and not key:
            return False, "unmapped_feature"
        
        table = self.tables[source]
        # Prefer exact developer key; only use exact feature label if no key exists.
        mapped_keys = {
            norm(value)
            for value in key.split(",")
            if norm(value)
        }
        
        candidates = []
        for row in table[3:]:
            row_key = norm(cell(row, 2))

            if mapped_keys and row_key.rstrip(",").strip() in mapped_keys:
                candidates.append(row)

        # If no developer-key match exists, try exact feature label.
        if not candidates and label:
            for row in table[3:]:
                row_label = norm(cell(row, 1))
                row_group = norm(cell(row, 0))

                if label in (row_label, row_group):
                    candidates.append(row)

        if not candidates:
            return False, "missing_or_ambiguous_permission_row"

        # Multiple rows may belong to the same feature.
        # Deny if matching rows contain conflicting permissions.
        permissions = {
            norm(cell(row, col))
            for row in candidates
            if norm(cell(row, col)) in ("yes", "no")
        }

        if len(permissions) != 1:
            return False, "missing_or_ambiguous_permission_row"

        return ("yes" in permissions, "permission_checked")

    def lookup(self, feature, role, source, employee_type):
        allowed, reason = self.permission(feature, role, source, employee_type)
        if not allowed:
            return {'status': 'denied', 'reason': reason}
        guide = self.guides[norm(feature)]
        return {'status': 'ok', 'feature': guide.name, 'steps': guide.steps}
