from typing import Tuple, Any, Dict, List, Optional
from django.db import connection
from datetime import date, time, datetime
from decimal import Decimal
from pprint import pformat
from src.infra.contracts.connection_adapter import IConnectionAdapter
from src.infra.exceptions.query_exec_exception import QueryExecutionException
from src.app.transfer_objects.commands.business_cmd import (
    RegisterBusinessProfileCmd
)
from src.app.transfer_objects.dto.business_dto import (
    BusinessListDTO,
    ResidentOwnerDTO,
    NonResidentOwnerDTO,
    OwnerBusinessDTO,
    BusinessInfoDTO,
)
from src.domain.contracts.business_repository_contract import (
    IBusinessRepository,
    IResidentOwnerRepository,
    INonResidentOwnerRepository,
)

try:
    from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
except Exception:
    InMemoryUploadedFile = TemporaryUploadedFile = tuple()

def _serialize_arg_for_log(v):
    """Make any value safe and readable for printing."""
    if isinstance(v, (datetime, date, time, Decimal)):
        return str(v)
    if isinstance(v, (list, tuple)):
        return [_serialize_arg_for_log(x) for x in v]
    if isinstance(v, dict):
        return {k: _serialize_arg_for_log(val) for k, val in v.items()}
    if isinstance(v, (InMemoryUploadedFile, TemporaryUploadedFile)):
        return {
            "filename": getattr(v, "name", None),
            "size": getattr(v, "size", None),
            "content_type": getattr(v, "content_type", None),
        }
    return v

PROC_NAME = "register_business_and_owner"

class BusinessRepository(IBusinessRepository):
    def __init__(self, ctx: IConnectionAdapter):
        self._ctx = ctx

    def fetch_business_list(self) -> list[BusinessListDTO]:
        try:
            sql = "SELECT * FROM get_business_summary();"
            rows = self._ctx.execute_query_to_dict(sql, [])
            print("SAMPLE ROW KEYS FETCH:", list(rows[0].keys()) if rows else [], flush=True)

            return self._map(rows)
        except Exception as e:
            raise QueryExecutionException(f"fetch_business_list failed: {e}") from e
        
    def search_business(self, search: str) -> list[BusinessListDTO]:
        try:
            sql = "SELECT * FROM search_business_summaries(%s)"
            rows = self._ctx.execute_query_to_dict(sql, [search])
            print("SAMPLE ROW KEYS SEARCH:", list(rows[0].keys()) if rows else [], flush=True)

            return self._map(rows)
        except Exception as e:
            raise QueryExecutionException(f"search_business failed: {e}") from e
        
    def sort_b_category(self, b_category_id: int) -> list[BusinessListDTO]:
        try:
            sql = "SELECT * FROM filter_business_summaries_by_category(%s)"
            rows = self._ctx.execute_query_to_dict(sql, [b_category_id])
            print("SAMPLE ROW KEYS CATEGORY:", list(rows[0].keys()) if rows else [], flush=True)

            return self._map(rows)
        except Exception as e:
            raise QueryExecutionException(f"sort_b_category failed: {e}") from e
        
    def sort_ownership_type(self, ownership_type_id: int) -> list[BusinessListDTO]:
        try:
            sql ="SELECT * FROM filter_business_summaries_by_ownership(%s)"
            rows = self._ctx.execute_query_to_dict(sql, [ownership_type_id])
            print("SAMPLE ROW KEYS OWNERSHIP:", list(rows[0].keys()) if rows else [], flush=True)

            return self._map(rows)
        except Exception as e:
            raise QueryExecutionException(f"sort_ownership_type failed: {e}") from e
    
    def sort_status(self, status_id: int) -> list[BusinessListDTO]:
        try:
            sql = "SELECT * FROM filter_business_summaries_by_status(%s)"
            rows = self._ctx.execute_query_to_dict(sql, [status_id])
            print("SAMPLE ROW KEYS STATUS:", list(rows[0].keys()) if rows else [], flush=True)

            return self._map(rows)
        except Exception as e:
            raise QueryExecutionException(f"sort_status failed: {e}") from e
    
    def _map(self, rows: list[dict]) -> list[BusinessListDTO]:
        # Ensure your SQL functions include ownership_type_name as a column.
        mapped: list[BusinessListDTO] = []
        for r in rows:
            mapped.append(
                BusinessListDTO(
                    business_id=r["business_id"],
                    business_name=r["business_name"],
                    business_category_name=r["business_category_name"],
                    business_nature=r["business_nature"],
                    business_owner_name=r["business_owner_name"],
                    business_address=r["business_address"],
                    business_status_name=r["business_status_name"],
                    ownership_type_name=r.get("ownership_type_name", ""),  # safe-get
                )
            )
        return mapped

    def _to_decimal(self, v: Any) -> Optional[Decimal]:
        if v in (None, "", "None"):
            return None
        try:
            return Decimal(str(v).replace(",", ""))
        except Exception:
            return None
        
    def _to_date(self, s: Any) -> Optional[date]:
        try:
            if isinstance(s, date):
                return s
            if isinstance(s, str) and s:
                return date.fromisoformat(s)
        except Exception:
            return None
        return None
    
    def _to_time(self, s: Any) -> Optional[time]:
        if isinstance(s, time):
            return s
        if isinstance(s, str) and s:
            try:
                parts = s.split(":")
                h = int(parts[0])
                m = int(parts[1])
                sec = int(parts[2]) if len(parts) > 2 else 0
                return time(h, m, sec)
            except Exception:
                return None
        return None
    
    def _to_int(self, v: Any) -> Optional[int]:
        if v in (None, "", "None"):
            return None
        try:
            return int(v)
        except Exception:
            return None
        
    def _upper_or_none(self, v: Any) -> Optional[str]:
        if v in (None, "", "None"):
            return None
        s = str(v).strip()
        return s.upper() if s else None
    
    def _upper_or_blank(self, v: Any) -> str:
        if v in (None, "", "None"):
            return ""
        return str(v).strip().upper()
    
    def register_business(self, cmd: RegisterBusinessProfileCmd) -> Tuple[int, int]:
        """
        Calls the RPC to register a business profile.

        Behavior:
          • If owner_person_id exists → treat as RESIDENT owner; only pass p_owner_person_id.
          • If owner_person_id is missing/empty/0 → treat as NON-RESIDENT; pass full personal info to create the person first.

        Returns:
          (business_id, owner_person_id)
        """
        
        o = cmd.owner or {}
        b = cmd.business or {}
        # proofs: List[str] = cmd.proof_attachment or []

        proofs: List[str] = list(
            getattr(cmd, "proof_files_saved", []) or getattr(cmd, "proof_attachment", []) or []
        )

        owner_person_id = self._to_int(o.get("owner_person_id") or o.get("person_id"))
        is_resident_owner = bool(owner_person_id)

        args: Dict[str, Any] = {
            "p_performer_staff_id": self._to_int(cmd.performer_staff_id),

            "p_owner_person_id" : owner_person_id,

            #business core
            "p_business_name": self._upper_or_blank(b.get("b_name")),
            "p_business_location_desc": b.get("b_desc"),
            "p_business_nature": b.get("b_nature"),
            "p_prev_yr_total_gross_sales": self._to_decimal(b.get("prevgross")),
            "p_date_est": self._to_date(b.get("date_est")),
            "p_dti_sec_reg_num": b.get("dti"),
            "p_capital_invested": self._to_decimal(b.get("capital_invested")),
            "p_mnthly_gross_incom_est": self._to_decimal(b.get("inc_est")),
            "p_num_of_emp": self._to_int(b.get("emp_num")),
            "p_ownership_type_id": self._to_int(b.get("ownership_type")),
            "p_operating_day_start": self._to_int(b.get("opt_days_start")),
            "p_operating_day_end": self._to_int(b.get("opt_days_end")),
            "p_operating_hour_start": self._to_time(b.get("opt_start")),
            "p_operating_hour_end": self._to_time(b.get("opt_end")),
            "p_business_city": self._upper_or_blank(b.get("city")),
            "p_business_barangay": self._upper_or_blank(b.get("barangay")),
            "p_business_street": self._upper_or_blank(b.get("street")),
            "p_business_purok_sitio_name": (b.get("purok_sitio") or None),
            "p_business_latitude": b.get("latitude"),
            "p_business_longitude": b.get("longitude"),
            "p_business_proof_files": proofs if proofs else None,
            "p_business_category_id": self._to_int(b.get("b_category")),
        }

        if is_resident_owner:
            args.update({
                "p_owner_last_name": None,
                "p_owner_first_name": None,
                "p_owner_middle_name": None,
                "p_owner_suffix": None,
                "p_owner_birthdate": None,
                "p_owner_email": None,
                "p_owner_mobile": None,
                "p_owner_sex_id": None,
                "p_owner_civil_status_id": None,
                "p_owner_nationality_id": None,
                "p_owner_religion_id": None,
                "p_owner_city": None,
                "p_owner_barangay": None,
                "p_owner_street": None,
                "p_owner_purok_sitio_name": None,
                # "p_owner_valid_id_front": None,
                # "p_owner_valid_id_back": None,
                # "p_owner_valid_id_type_id": None,
            })
        else:
            o: NonResidentOwnerDTO = cmd.owner
            args.update({
                "p_owner_last_name":        self._upper_or_blank(o.get("last_name")),
                "p_owner_first_name":       self._upper_or_blank(o.get("first_name")),
                "p_owner_middle_name":      self._upper_or_none(o.get("middle_name")),
                "p_owner_suffix":           self._upper_or_none(o.get("suffix")),
                "p_owner_birthdate":        self._to_date(o.get("dob") or o.get("date_of_birth")),
                "p_owner_email":            o.get("email"),
                "p_owner_mobile":           o.get("mobile"),
                "p_owner_sex_id":           self._to_int(o.get("sex_id") or o.get("sex")),
                "p_owner_civil_status_id":  self._to_int(o.get("civil_status_id")),
                "p_owner_nationality_id":   self._to_int(o.get("nationality_id")),
                "p_owner_religion_id":      self._to_int(o.get("religion_id")),

                "p_owner_city":             self._upper_or_blank(o.get("city")),
                "p_owner_barangay":         self._upper_or_blank(o.get("barangay")),
                "p_owner_street":           self._upper_or_blank(o.get("street")),
                "p_owner_purok_sitio_name": (o.get("purok_sitio") or None),

                # ✅ ID docs
                # "p_owner_valid_id_front":   (o.get("id_front_path") or cmd.owner_id_front_path),
                # "p_owner_valid_id_back":    (o.get("id_back_path")  or cmd.owner_id_back_path),
                # "p_owner_valid_id_type_id": self._to_int(o.get("valid_id_type_id") or cmd.owner_valid_id_type_id),
            })
        param_order = [
            "p_performer_staff_id",

            # ===== Business =====
            "p_business_name",
            "p_business_location_desc",
            "p_business_nature",
            "p_prev_yr_total_gross_sales",
            "p_date_est",
            "p_dti_sec_reg_num",
            "p_capital_invested",
            "p_mnthly_gross_incom_est",
            "p_num_of_emp",
            "p_ownership_type_id",

            # operating schedule
            "p_operating_day_start",
            "p_operating_day_end",
            "p_operating_hour_start",
            "p_operating_hour_end",

            # business address (+ geo)
            "p_business_city",
            "p_business_barangay",
            "p_business_street",
            "p_business_purok_sitio_name",
            "p_business_latitude",
            "p_business_longitude",

            # multi-image proof files
            "p_business_proof_files",

            # optional business category
            "p_business_category_id",

            # use this if owner already exists
            "p_owner_person_id",

            # ===== Owner (creation only) =====
            "p_owner_last_name",
            "p_owner_first_name",
            "p_owner_middle_name",
            "p_owner_suffix",
            "p_owner_birthdate",
            "p_owner_email",
            "p_owner_mobile",
            "p_owner_sex_id",
            "p_owner_civil_status_id",
            "p_owner_nationality_id",
            "p_owner_religion_id",

            # Owner address
            "p_owner_city",
            "p_owner_barangay",
            "p_owner_street",
            "p_owner_purok_sitio_name",

            # Optional files for owner
            # "p_owner_valid_id_front",
            # "p_owner_valid_id_back",
            # "p_owner_valid_id_type_id",
        ]

        placeholders = ", ".join([f"%({k})s" for k in param_order])
        # sql = f"SELECT * FROM {PROC_NAME}({placeholders}) AS t(business_id INT, owner_person_id INT)"
        sql = f"SELECT * FROM {PROC_NAME}({placeholders})"

        safe_args = {k: _serialize_arg_for_log(v) for k, v in (args or {}).items()}
        print(f"\n[{PROC_NAME}] About to execute:")
        print(f"SQL : {sql}")
        print(f"ARGS: {pformat(safe_args, width=100)}\n")

        with connection.cursor() as cur:
            cur.execute(sql, args)
            row = cur.fetchone()
            if not row:
                raise RuntimeError("Stored procedure returned no rows.")
            return int(row[0]), int(row[1])

    def fetch_business_pins(
        self,
        *,
        search: Optional[str] = None,
        b_category: Optional[int] = None,
        ownership_type: Optional[int] = None,
        status: Optional[int] = None,
    ) -> list[dict]:
        """
        Returns pins with optional filters. Filters are bound via a CTE to avoid
        repeating placeholders and to keep the WHERE tidy.
        """
        try:
            sql = """
                WITH params AS (
                SELECT
                    %s::int  AS p_status,
                    %s::int  AS p_category,
                    %s::int  AS p_ownership,
                    %s::text AS p_search
                )
                SELECT
                b.business_id,
                b.business_name,
                b.business_nature,
                bc.purpose_label          AS business_category,
                bs.business_status_name   AS status,
                ot.ownership_type_name    AS ownership_type,
                a.latitude::float8        AS lat,
                a.longitude::float8       AS lng,
                a.street,
                a.barangay,
                a.city,
                a.purok_sitio_id,
                ps.purok_sitio_name       AS purok
                FROM public.business AS b
                JOIN public.addresss AS a
                ON a.address_id = b.address_id
                LEFT JOIN public.document_purpose AS bc
                ON bc.document_purpose_id = b.business_category_id
                LEFT JOIN public.business_status   AS bs
                ON bs.business_status_id   = b.business_status_id
                LEFT JOIN public.ownership_type    AS ot
                ON ot.ownership_type_id    = b.ownership_type_id
                LEFT JOIN public.purok_sitio       AS ps
                ON ps.purok_sitio_id       = a.purok_sitio_id
                CROSS JOIN params p
                WHERE a.latitude  IS NOT NULL
                AND a.longitude IS NOT NULL
                AND b.business_status_id   = COALESCE(p.p_status,   b.business_status_id)
                AND b.business_category_id = COALESCE(p.p_category, b.business_category_id)
                AND b.ownership_type_id    = COALESCE(p.p_ownership, b.ownership_type_id)
                AND (
                    COALESCE(p.p_search,'') = '' OR
                    b.business_name ILIKE '%%' || p.p_search || '%%' OR
                    COALESCE(b.business_nature,'') ILIKE '%%' || p.p_search || '%%' OR
                    COALESCE(a.street,'')          ILIKE '%%' || p.p_search || '%%'
                )
                ORDER BY b.business_name;
            """

            # Only 4 params, matching the CTE order:
            params = [
                status,          # %s::int  -> p_status
                b_category,      # %s::int  -> p_category
                ownership_type,  # %s::int  -> p_ownership
                (search or None) # %s::text -> p_search
            ]

            return self._ctx.execute_query_to_dict(sql, params) or []

        except Exception as e:
            # Your exception requires a positional 'code'. Provide one (e.g., "E_DB").
            # If your class supports kwargs, you could do: QueryExecutionException(str(e), code="E_DB")
            raise QueryExecutionException(f"fetch_business_pins failed: {e}", "E_DB")

class ResidentOwnerRepository(IResidentOwnerRepository):
    def __init__(self, ctx: IConnectionAdapter):
        self._ctx = ctx

    def search_owner(self, search: str, *, only_nonresident: bool = False) -> list[ResidentOwnerDTO]:
        try: 
            if only_nonresident:
                sql = "SELECT * FROM search_person_by_code_or_name(%s)"
                rows = self._ctx.execute_query_to_dict(sql, [search])

            else:
                sql = "SELECT * FROM search_person_by_code_or_name(%s)"
                rows = self._ctx.execute_query_to_dict(sql, [search])

            def _addr(r: dict) -> str | None:
                parts = [r.get("street"), r.get("purok"), r.get("barangay"), r.get("city")]
                joined = ", ".join(p for p in parts if p and str(p).strip() != "")
                return joined or None

            return [
                ResidentOwnerDTO(
                    person_id=r["person_id"],
                    person_code=r.get("person_code"),
                    full_name=r.get("person_name"),
                    address_line=_addr(r),
                    street=r.get("street"),
                    purok=r.get("purok"),
                    barangay=r.get("barangay"),
                    city=r.get("city"),
                    # fields your SQL doesn't return yet — leave None
                    sex_name=None,
                    date_of_birth=None,
                    residential_status_name=None,
                    civil_status=None,
                    nationality=None,
                    religion=None,
                    mobile=None,
                    email=None,
                )
                for r in rows or []
            ]

        except Exception as e:
            raise QueryExecutionException(f"search_owner failed: {e}") from e
        
    def get_owner_details(self, person_id: int) -> list[ResidentOwnerDTO]:
        try:
            sql = "SELECT * FROM get_details(%s)"
            rows = self._ctx.execute_query_to_dict(sql, [person_id]) or []

            if not rows:
                return None
            r = rows[0]

            def _addr(r: dict) -> str | None:
                parts = [r.get("street"), r.get("purok"), r.get("barangay"), r.get("city")]
                parts = [p for p in parts if p and str(p).strip()]
                return ", ".join(parts) if parts else None
            
            def _compose_full_name(r: dict) -> str:
                last   = (r.get("last_name") or "").strip()
                first  = (r.get("first_name") or "").strip()
                middle = (r.get("middle_name") or "").strip()
                suffix = (r.get("suffix") or "").strip()

                # build "LAST, FIRST"
                main = ", ".join([x for x in (last, first) if x])

                # middle initial "M." only if middle exists
                mi = f"{middle[0]}." if middle else ""

                parts = [p for p in (main, mi, suffix) if p]
                return " ".join(parts) if parts else ""
            
            full_name = r.get("full_name") or _compose_full_name(r)

            return ResidentOwnerDTO(
                person_id=r["person_id"],
                person_code=r.get("person_code"),
                full_name=full_name,
                sex_name=r.get("sex"),
                date_of_birth=r.get("birthdate"),
                residential_status_name= r.get("residential_status"),
                civil_status=r.get("civil_status"),
                nationality=r.get("nationality"),
                religion=r.get("religion"),
                mobile=r.get("mobile_num"),
                email=r.get("email"),
                street=r.get("street"),
                purok=r.get("purok"),
                barangay=r.get("barangay"),
                city=r.get("city"),
                address_line=_addr(r),
            )
        except Exception as e:
            raise QueryExecutionException(f"get_owner_details failed: {e}") from e
        
class OwnerBusinessInformationRepository:
    def __init__(self, ctx:IConnectionAdapter):
        self._ctx = ctx

    def get_business_information(self, business_id: int) -> list[OwnerBusinessDTO]:
        try:
            sql = "SELECT * FROM get_business_details(%s)"
            rows = self._ctx.execute_query_to_dict(sql, [business_id]) or []

            return rows[0] if rows else {}
        except Exception as e:
            raise QueryExecutionException(f"get_business_information failed: {e}") from e
        
    def get_owner_information(self, person_id: int) -> list[OwnerBusinessDTO]:
        try:
            sql = "SELECT * FROM get_details(%s)"
            rows = self._ctx.execute_query_to_dict(sql, [person_id]) or []

            return rows[0] if rows else {}
        except Exception as e:
            raise QueryExecutionException(f"get_owner_information failed: {e}") from e