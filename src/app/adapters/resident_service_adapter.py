from src.app.contracts.resident_service_contract import IResidentService
from src.infra.repositories.queries.person_queries import PersonQuery


class ResidentServiceAdapter:
    
    def __init__(self, resident_service: IResidentService, person_query: PersonQuery):
        self._resident_service = resident_service
        self._person_query = person_query

    def get_minors_under5_active(self) -> list[dict]:
        """Return shaped list of minors under 5: deduped and formatted.

        Output shape: [{'person_id': int, 'full_name': str, 'address': str}, ...]
        - full_name: `FIRST M. LAST [SUFFIX]` (middle initial when available)
        - address: `street, purok_name, Brgy {barangay}, city` (parts omitted when empty)
        Deduplicates by `person_id` and prefers records that contain an address.
        """
        rows = self._person_query.get_minors_under5_active(limit=10)
        result_map: dict[int, dict] = {}

        for r in rows:
            pid = r.get('person_id')
            if pid is None:
                continue

            first = (r.get('first_name') or '').strip()
            middle = (r.get('middle_name') or '').strip()
            last = (r.get('last_name') or '').strip()
            suffix = (r.get('suffix') or '').strip()

            mid_initial = f" {middle[0].upper()}." if middle else ''
            full_name = (f"{first}{mid_initial} {last}".strip())
            if suffix:
                # normalize suffix (keep as-is), append after name
                full_name = f"{full_name} {suffix}".strip()

            street = (r.get('street') or '').strip()
            purok = (r.get('purok_name') or '').strip()
            barangay = (r.get('barangay') or '').strip()
            city = (r.get('city') or '').strip()

            parts: list[str] = []
            if street:
                parts.append(street)
            if purok:
                parts.append(purok)
            if barangay:
                parts.append(f"Brgy {barangay}")
            if city:
                parts.append(city)

            address = ', '.join(parts)

            new_rec = {'person_id': pid, 'full_name': full_name, 'address': address}

            existing = result_map.get(pid)
            # Prefer a record with address over one without; otherwise keep the first
            if existing is None:
                result_map[pid] = new_rec
            else:
                if not existing.get('address') and address:
                    result_map[pid] = new_rec

        # Return list preserving insertion order of first-seen person_ids
        return list(result_map.values())