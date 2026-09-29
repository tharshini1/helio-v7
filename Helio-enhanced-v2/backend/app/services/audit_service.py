import json

from app.models.audit_log import AuditLog


class AuditService:

    @staticmethod
    def record(
        db,
        patient_id,
        agent,
        action,
        status,
        details=None,
    ):

        log = AuditLog(
            patient_id=patient_id,
            agent=agent,
            action=action,
            status=status,
            details=(
                json.dumps(details)
                if details
                else None
            ),
        )

        db.add(log)
        db.commit()
        db.refresh(log)

        return log