from src.infra.contracts.connection_adapter import IConnectionAdapter


class MaternalHealthRecordQueries:
    
    def __init__(self, connection: IConnectionAdapter):
        self._connection = connection
    
    def get_by_maternal_health_record_id(self, maternal_health_record_id: int) -> dict | None:
        """Return the maternal health record row as a dict for the given id.

        Returns None when no row is found.
        """
        sql = "SELECT * FROM maternal_health_record WHERE maternal_health_record_id = %s"
        try:
            rows = self._connection.execute_query_to_dict(sql, (maternal_health_record_id,))
            if rows:
                return rows[0]
            return None
        except Exception:
            # Let caller handle/log exceptions
            raise

    def get_child_by_maternal_record_id(self, maternal_health_record_id: int) -> dict | None:
        """Compatibility wrapper: resolve the mother (person_id) for the given
        `maternal_health_record_id` and return the most relevant child_health_record
        for that mother.

        This method preserves the previous API but delegates to
        `get_child_by_mother_id` which accepts a `mother_id` directly.
        """
        # Resolve the maternal health record to get the mother's person_id
        mhr = self.get_by_maternal_health_record_id(maternal_health_record_id)
        if not mhr:
            return None
        mother_id = mhr.get("person_id")
        if mother_id is None:
            return None
        return self.get_child_by_mother_id(mother_id)

    def get_child_by_mother_id(self, mother_id: int) -> dict | None:
        """Return the most relevant child_health_record row for the given `mother_id`.

        The method looks up rows in `child_health_record` where `mother_id` matches
        the provided value and returns the most recently created record (tiebreak
        by `child_record_id`). Returns None when no child record is found.
        """
        sql = (
            "SELECT c.* FROM child_health_record c "
            "WHERE c.mother_id = %s "
            "ORDER BY c.created_at DESC, c.child_record_id DESC "
        )
        try:
            rows = self._connection.execute_query_to_dict(sql, (mother_id,))
            return rows[0] if rows else None
        except Exception:
            # Let caller handle/log exceptions
            raise

    def get_active_maternal_record_by_person_id(self, person_id: int) -> dict | None:
        """Return the most recent active maternal_health_record for a person (record_status_id = 1).

        Returns None when no active record is found.
        """
        sql = (
            "SELECT m.* FROM maternal_health_record m "
            "WHERE m.person_id = %s AND m.record_status_id = 1 "
            "ORDER BY m.created_at DESC, m.maternal_record_id DESC LIMIT 1"
        )
        try:
            rows = self._connection.execute_query_to_dict(sql, (person_id,))
            return rows[0] if rows else None
        except Exception:
            raise

    def get_obstetric_history_by_mhr_id(self, maternal_record_id: int) -> list:
        sql = "SELECT * FROM obstetric_history WHERE maternal_record_id = %s ORDER BY obstetric_history_id DESC"
        try:
            rows = self._connection.execute_query_to_dict(sql, (maternal_record_id,))
            return rows or []
        except Exception:
            raise

    def get_medical_history_by_mhr_id(self, maternal_record_id: int) -> list:
        sql = "SELECT * FROM medical_history WHERE maternal_record_id = %s ORDER BY medical_history_id DESC"
        try:
            rows = self._connection.execute_query_to_dict(sql, (maternal_record_id,))
            return rows or []
        except Exception:
            raise

    def get_anc_visits_by_mhr_id(self, maternal_record_id: int) -> list:
        sql = "SELECT * FROM maternal_anc_visit WHERE maternal_record_id = %s ORDER BY visit_date DESC, anc_visit_id DESC"
        try:
            rows = self._connection.execute_query_to_dict(sql, (maternal_record_id,))
            return rows or []
        except Exception:
            raise

    def get_anc_visit_by_id(self, anc_visit_id: int) -> dict | None:
        sql = "SELECT * FROM maternal_anc_visit WHERE anc_visit_id = %s LIMIT 1"
        try:
            rows = self._connection.execute_query_to_dict(sql, (anc_visit_id,))
            return rows[0] if rows else None
        except Exception:
            raise

    def get_previous_pregnancies_by_mhr_id(self, maternal_record_id: int) -> list:
        sql = "SELECT * FROM previous_pregnancy_info WHERE maternal_record_id = %s ORDER BY date_of_deliveries DESC"
        try:
            rows = self._connection.execute_query_to_dict(sql, (maternal_record_id,))
            return rows or []
        except Exception:
            raise

    def get_delivery_types(self) -> list:
        sql = "SELECT * FROM delivery_type ORDER BY delivery_type_id"
        try:
            rows = self._connection.execute_query_to_dict(sql, None)
            return rows or []
        except Exception:
            raise

    def get_tt_vaccine_records_by_mhr_id(self, maternal_record_id: int) -> list:
        sql = "SELECT ttr.*, tt.tt_type_name FROM tt_vaccine_record ttr LEFT JOIN tt_type tt ON tt.tt_type_id = ttr.tt_type_id WHERE ttr.maternal_record_id = %s ORDER BY ttr.date_given DESC"
        try:
            rows = self._connection.execute_query_to_dict(sql, (maternal_record_id,))
            return rows or []
        except Exception:
            raise

    def get_tt_types(self) -> list:
        sql = "SELECT * FROM tt_type ORDER BY tt_type_id"
        try:
            rows = self._connection.execute_query_to_dict(sql, None)
            return rows or []
        except Exception:
            raise

    def get_present_pregnancy_status_by_mhr_id(self, maternal_record_id: int) -> dict | None:
        sql = "SELECT * FROM present_pregnancy_status WHERE maternal_record_id = %s ORDER BY preg_status_id DESC LIMIT 1"
        try:
            rows = self._connection.execute_query_to_dict(sql, (maternal_record_id,))
            return rows[0] if rows else None
        except Exception:
            raise

    def get_lab_results_by_mhr_id(self, maternal_record_id: int) -> list:
        sql = "SELECT * FROM lab_result WHERE maternal_record_id = %s ORDER BY date_tested DESC"
        try:
            rows = self._connection.execute_query_to_dict(sql, (maternal_record_id,))
            return rows or []
        except Exception:
            raise

    def get_maternal_checklist_by_mhr_id(self, maternal_record_id: int) -> list:
        sql = "SELECT mc.*, ci.checklist_name FROM maternal_checklist mc LEFT JOIN checklist_item ci ON ci.checklist_item_id = mc.checklist_item_id WHERE mc.maternal_record_id = %s"
        try:
            rows = self._connection.execute_query_to_dict(sql, (maternal_record_id,))
            return rows or []
        except Exception:
            raise

    def get_plan_and_baseline_by_mhr_id(self, maternal_record_id: int) -> dict | None:
        sql = "SELECT * FROM plan_and_baseline WHERE maternal_record_id = %s ORDER BY plan_and_baseline_id DESC LIMIT 1"
        try:
            rows = self._connection.execute_query_to_dict(sql, (maternal_record_id,))
            return rows[0] if rows else None
        except Exception:
            raise

    def get_micronutrients_by_mhr_id(self, maternal_record_id: int) -> dict | None:
        sql = "SELECT * FROM micronutrients WHERE maternal_record_id = %s ORDER BY micronutrients_id DESC LIMIT 1"
        try:
            rows = self._connection.execute_query_to_dict(sql, (maternal_record_id,))
            return rows[0] if rows else None
        except Exception:
            raise

    def get_risk_responses_by_mhr_id(self, maternal_record_id: int) -> list:
        sql = "SELECT rr.*, rc.risk_category_name FROM risk_response rr LEFT JOIN risk_category rc ON rc.risk_category_id = rr.risk_category_id WHERE rr.maternal_record_id = %s"
        try:
            rows = self._connection.execute_query_to_dict(sql, (maternal_record_id,))
            return rows or []
        except Exception:
            raise

    def get_maternal_visit_schedules_by_mhr_id(self, maternal_record_id: int) -> list:
        sql = "SELECT * FROM maternal_visit_schedule WHERE maternal_record_id = %s ORDER BY scheduled_date DESC"
        try:
            rows = self._connection.execute_query_to_dict(sql, (maternal_record_id,))
            return rows or []
        except Exception:
            raise

    def get_maternal_anc_rows_by_mhr_id(self, maternal_record_id: int) -> list:
        """Return all maternal ANC (prenatal) visit rows for a maternal health record.
        
        Returns list of ANC row dicts ordered by visit date (most recent first).
        """
        sql = "SELECT * FROM maternal_anc_row WHERE maternal_record_id = %s ORDER BY anc_date DESC, anc_row_id DESC"
        try:
            rows = self._connection.execute_query_to_dict(sql, (maternal_record_id,))
            return rows or []
        except Exception:
            raise

    def get_maternal_anc_row_by_id(self, anc_row_id: int) -> dict | None:
        """Return a single maternal ANC row by its ID.
        
        Returns None when no row is found.
        """
        sql = "SELECT * FROM maternal_anc_row WHERE anc_row_id = %s LIMIT 1"
        try:
            rows = self._connection.execute_query_to_dict(sql, (anc_row_id,))
            return rows[0] if rows else None
        except Exception:
            raise

    def get_maternal_anc_rows_by_visit_id(self, anc_visit_id: int) -> list:
        """Return all maternal ANC rows for a specific ANC visit.
        
        Returns list of ANC row dicts ordered by visit date (most recent first).
        """
        sql = "SELECT * FROM maternal_anc_row WHERE anc_visit_id = %s ORDER BY anc_date DESC, anc_row_id DESC"
        try:
            rows = self._connection.execute_query_to_dict(sql, (anc_visit_id,))
            return rows or []
        except Exception:
            raise

    def get_latest_maternal_anc_row_by_mhr_id(self, maternal_record_id: int) -> dict | None:
        """Return the most recent maternal ANC row for a maternal health record.
        
        Returns None when no row is found.
        """
        sql = "SELECT * FROM maternal_anc_row WHERE maternal_record_id = %s ORDER BY anc_date DESC, anc_row_id DESC LIMIT 1"
        try:
            rows = self._connection.execute_query_to_dict(sql, (maternal_record_id,))
            return rows[0] if rows else None
        except Exception:
            raise

    def get_maternal_anc_rows_by_date_range(self, maternal_record_id: int, start_date: str, end_date: str) -> list:
        """Return maternal ANC rows within a specific date range.
        
        Args:
            maternal_record_id: The maternal health record ID
            start_date: Start date (inclusive) in format 'YYYY-MM-DD'
            end_date: End date (inclusive) in format 'YYYY-MM-DD'
        
        Returns list of ANC row dicts ordered by visit date (most recent first).
        """
        sql = (
            "SELECT * FROM maternal_anc_row "
            "WHERE maternal_record_id = %s AND anc_date >= %s AND anc_date <= %s "
            "ORDER BY anc_date DESC, anc_row_id DESC"
        )
        try:
            rows = self._connection.execute_query_to_dict(sql, (maternal_record_id, start_date, end_date))
            return rows or []
        except Exception:
            raise

    def count_maternal_anc_rows_by_mhr_id(self, maternal_record_id: int) -> int:
        """Return the count of maternal ANC rows for a maternal health record.
        
        Returns 0 when no rows are found.
        """
        sql = "SELECT COUNT(*) as count FROM maternal_anc_row WHERE maternal_record_id = %s"
        try:
            rows = self._connection.execute_query_to_dict(sql, (maternal_record_id,))
            return rows[0]['count'] if rows else 0
        except Exception:
            raise

    def get_postpartum_visit_rows_by_mhr_id(self, maternal_record_id: int) -> list:
        """Return all postpartum visit rows for a maternal health record.
        
        Returns list of postpartum visit row dicts ordered by visit date (most recent first).
        """
        sql = "SELECT * FROM postpartum_visit_row WHERE maternal_record_id = %s ORDER BY date_visit DESC, pp_row_id DESC"
        try:
            rows = self._connection.execute_query_to_dict(sql, (maternal_record_id,))
            return rows or []
        except Exception:
            raise

    def get_postpartum_visit_rows_with_feeding_type_by_mhr_id(self, maternal_record_id: int) -> list:
        """Return all postpartum visit rows with feeding type names joined.
        
        Joins postpartum_visit_row with feeding_type to include feeding_type_name.
        Returns list ordered by visit date (most recent first).
        """
        sql = (
            "SELECT ppvr.*, ft.feeding_type_name "
            "FROM postpartum_visit_row ppvr "
            "LEFT JOIN feeding_type ft ON ft.feeding_type_id = ppvr.feeding_type_id "
            "WHERE ppvr.maternal_record_id = %s "
            "ORDER BY ppvr.date_visit DESC, ppvr.pp_row_id DESC"
        )
        try:
            rows = self._connection.execute_query_to_dict(sql, (maternal_record_id,))
            return rows or []
        except Exception:
            raise

    def get_postpartum_visit_row_by_id(self, pp_row_id: int) -> dict | None:
        """Return a single postpartum visit row by its ID.
        
        Returns None when no row is found.
        """
        sql = "SELECT * FROM postpartum_visit_row WHERE pp_row_id = %s LIMIT 1"
        try:
            rows = self._connection.execute_query_to_dict(sql, (pp_row_id,))
            return rows[0] if rows else None
        except Exception:
            raise

    def get_postpartum_visit_row_with_feeding_type_by_id(self, pp_row_id: int) -> dict | None:
        """Return a single postpartum visit row with feeding type name joined.
        
        Joins postpartum_visit_row with feeding_type to include feeding_type_name.
        Returns None when no row is found.
        """
        sql = (
            "SELECT ppvr.*, ft.feeding_type_name "
            "FROM postpartum_visit_row ppvr "
            "LEFT JOIN feeding_type ft ON ft.feeding_type_id = ppvr.feeding_type_id "
            "WHERE ppvr.pp_row_id = %s LIMIT 1"
        )
        try:
            rows = self._connection.execute_query_to_dict(sql, (pp_row_id,))
            return rows[0] if rows else None
        except Exception:
            raise
        
    def get_postpartum_visit_row_with_feeding_type_by_mhr_id(self, maternal_record_id: int) -> dict | None:
        """Return a single postpartum visit row with feeding type name joined.
        
        Joins postpartum_visit_row with feeding_type to include feeding_type_name.
        Returns None when no row is found.
        """
        sql = (
            "SELECT ppvr.*, ft.feeding_type_name "
            "FROM postpartum_visit_row ppvr "
            "LEFT JOIN feeding_type ft ON ft.feeding_type_id = ppvr.feeding_type_id "
            "WHERE ppvr.maternal_record_id = %s LIMIT 1"
        )
        try:
            rows = self._connection.execute_query_to_dict(sql, (maternal_record_id,))
            return rows[0] if rows else None
        except Exception:
            raise


    def get_feeding_types(self) -> list:
        """Return all feeding types ordered by ID.
        
        Returns list of feeding type dicts (feeding_type_id, feeding_type_name).
        """
        sql = "SELECT * FROM feeding_type ORDER BY feeding_type_id"
        try:
            rows = self._connection.execute_query_to_dict(sql, None)
            return rows or []
        except Exception:
            raise

    def _assemble_full_record(self, mhr_row: dict) -> dict:
        """Internal helper to assemble full maternal record payload from a base mhr row."""
        if not mhr_row:
            return {}
        mhr_id = mhr_row.get('maternal_record_id') or mhr_row.get('maternal_record_id')
        # base record copy
        record = dict(mhr_row)

        try:
            # attach bmi status name if available
            try:
                if record.get('bmi_status_id') is not None:
                    bsql = "SELECT bmi_status_name FROM bmi_status WHERE bmi_status_id = %s LIMIT 1"
                    brows = self._connection.execute_query_to_dict(bsql, (record.get('bmi_status_id'),))
                    record['bmi_status'] = brows[0] if brows else None
                else:
                    record['bmi_status'] = None
            except Exception:
                record['bmi_status'] = None

            # related lists / records
            record['obstetric_history'] = self.get_obstetric_history_by_mhr_id(mhr_id)
            record['medical_history'] = self.get_medical_history_by_mhr_id(mhr_id)
            record['anc_visits'] = self.get_anc_visits_by_mhr_id(mhr_id)
            record['previous_pregnancies'] = self.get_previous_pregnancies_by_mhr_id(mhr_id)
            record['delivery_types'] = self.get_delivery_types()
            record['tt_vaccine_records'] = self.get_tt_vaccine_records_by_mhr_id(mhr_id)
            record['tt_types'] = self.get_tt_types()
            record['present_pregnancy_status'] = self.get_present_pregnancy_status_by_mhr_id(mhr_id)
            record['lab_results'] = self.get_lab_results_by_mhr_id(mhr_id)
            record['micronutrients'] = self.get_micronutrients_by_mhr_id(mhr_id)
            record['risk_responses'] = self.get_risk_responses_by_mhr_id(mhr_id)
            record['maternal_checklist'] = self.get_maternal_checklist_by_mhr_id(mhr_id)
            record['plan_and_baseline'] = self.get_plan_and_baseline_by_mhr_id(mhr_id)
            record['maternal_visit_schedules'] = self.get_maternal_visit_schedules_by_mhr_id(mhr_id)
            record['anc_rows'] = self.get_maternal_anc_rows_by_mhr_id(mhr_id)
            record['postpartum_visit_rows'] = self.get_postpartum_visit_rows_with_feeding_type_by_mhr_id(mhr_id)
            record['feeding_types'] = self.get_feeding_types()
        except Exception:
            # if any part fails, still return what we have
            pass

        return record

    def get_entire_maternal_record_by_person_id(self, person_id: int) -> dict | None:
        """Return a fully assembled maternal health record (and related data) for a person_id.

        Returns None when no maternal record is found.
        """
        sql = "SELECT * FROM maternal_health_record WHERE person_id = %s ORDER BY created_at DESC, maternal_record_id DESC LIMIT 1"
        try:
            rows = self._connection.execute_query_to_dict(sql, (person_id,))
            if not rows:
                return None
            mhr = rows[0]
            return self._assemble_full_record(mhr)
        except Exception:
            raise

    def get_entire_maternal_record_by_husband_id(self, husband_id: int) -> dict | None:
        """Return a fully assembled maternal health record (and related data) for a husband_id.

        Returns None when no maternal record is found.
        """
        sql = "SELECT * FROM maternal_health_record WHERE husband_id = %s ORDER BY created_at DESC, maternal_record_id DESC LIMIT 1"
        try:
            rows = self._connection.execute_query_to_dict(sql, (husband_id,))
            if not rows:
                return None
            mhr = rows[0]
            return self._assemble_full_record(mhr)
        except Exception:
            raise