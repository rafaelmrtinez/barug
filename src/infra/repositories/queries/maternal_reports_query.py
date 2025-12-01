from typing import Dict, List, Any
from src.infra.contracts.connection_adapter import IConnectionAdapter


class MaternalReportsQuery:
    
    def __init__(self, db: IConnectionAdapter):
        self._db = db

    # ===== MONTHLY REPORTS =====
    
    def get_monthly_visit_compliance(self, year: int, month: int) -> Dict[str, Any]:
        """
        Monthly Maternal Visit Compliance Dashboard
        - Total visits, missed visits, % compliance, high-risk cases flagged
        - Enables proactive follow-ups and targeted home visits
        """
        query = """
        WITH monthly_visits AS (
            SELECT 
                mvs.maternal_visit_schedule_id,
                mvs.maternal_record_id,
                mvs.scheduled_date,
                mvs.date_time_completed,
                mvs.status_id,
                rs.record_status_name AS status_name,
                mvs.marked_completed_by_id,
                CASE 
                    WHEN mvs.date_time_completed IS NOT NULL AND mvs.scheduled_date IS NOT NULL
                    THEN mvs.date_time_completed::date - mvs.scheduled_date
                    ELSE NULL
                END AS delay_days
            FROM maternal_visit_schedule mvs
            LEFT JOIN record_status rs ON mvs.status_id = rs.record_status_id
            WHERE DATE_PART('year', mvs.scheduled_date) = %s
              AND DATE_PART('month', mvs.scheduled_date) = %s
        ),
        visit_summary AS (
            SELECT 
                COUNT(*) AS total_scheduled,
                COUNT(CASE WHEN status_id = 2 THEN 1 END) AS completed_visits,
                COUNT(CASE WHEN status_id = 3 THEN 1 END) AS missed_visits,
                COUNT(CASE WHEN delay_days > 0 THEN 1 END) AS delayed_visits,
                ROUND(AVG(CASE WHEN delay_days > 0 THEN delay_days END)::numeric, 2) AS avg_delay_days,
                ROUND(COUNT(CASE WHEN status_id = 2 THEN 1 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) AS compliance_rate
            FROM monthly_visits
        ),
        high_risk_cases AS (
            SELECT 
                mhr.maternal_record_id,
                p.first_name || ' ' || p.last_name AS mother_name,
                COUNT(DISTINCT rr.risk_response_id) AS risk_count,
                STRING_AGG(DISTINCT rc.risk_category_name, ', ') AS risk_categories,
                COUNT(CASE WHEN mv.status_id = 3 THEN 1 END) AS missed_visits
            FROM maternal_health_record mhr
            JOIN person p ON mhr.person_id = p.person_id
            LEFT JOIN risk_response rr ON mhr.maternal_record_id = rr.maternal_record_id
            LEFT JOIN risk_category rc ON rr.risk_category_id = rc.risk_category_id
            LEFT JOIN monthly_visits mv ON mhr.maternal_record_id = mv.maternal_record_id
            WHERE mhr.is_transferred = false
            GROUP BY mhr.maternal_record_id, p.first_name, p.last_name
            HAVING COUNT(DISTINCT rr.risk_response_id) > 0 OR COUNT(CASE WHEN mv.status_id = 3 THEN 1 END) >= 2
            ORDER BY risk_count DESC, missed_visits DESC
        ),
        mother_compliance AS (
            SELECT 
                mhr.maternal_record_id,
                p.first_name || ' ' || p.last_name AS mother_name,
                COUNT(DISTINCT mv.maternal_visit_schedule_id) AS total_visits,
                COUNT(CASE WHEN mv.status_id = 2 THEN 1 END) AS completed,
                COUNT(CASE WHEN mv.status_id = 3 THEN 1 END) AS missed,
                ROUND(COUNT(CASE WHEN mv.status_id = 2 THEN 1 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) AS compliance_pct
            FROM maternal_health_record mhr
            JOIN person p ON mhr.person_id = p.person_id
            LEFT JOIN monthly_visits mv ON mhr.maternal_record_id = mv.maternal_record_id
            WHERE mhr.is_transferred = false
            GROUP BY mhr.maternal_record_id, p.first_name, p.last_name
            HAVING COUNT(DISTINCT mv.maternal_visit_schedule_id) > 0
            ORDER BY compliance_pct ASC
        )
        SELECT 
            (SELECT row_to_json(vs) FROM visit_summary vs) AS visit_summary,
            (SELECT json_agg(hrc) FROM high_risk_cases hrc) AS high_risk_cases,
            (SELECT json_agg(mc) FROM mother_compliance mc) AS mother_compliance
        """
        
        result = self._db.execute_query_to_dict(query, (year, month))
        return result[0] if result else {}

    def get_monthly_risk_indicator_summary(self, year: int, month: int) -> Dict[str, Any]:
        """
        Monthly Maternal Risk Indicator Summary
        - Summarizes mothers tagged with risk factors during the month
        - KPIs: anemia, hypertension, underweight, teen pregnancy, prior complications
        """
        query = """
        WITH monthly_anc_visits AS (
            SELECT 
                mav.anc_visit_id,
                mav.maternal_record_id,
                mav.visit_date,
                mav.trimester_stage_id,
                mhr.person_id,
                p.birthdate,
                mhr.bmi_status_id,
                bs.bmi_status_name
            FROM maternal_anc_visit mav
            JOIN maternal_health_record mhr ON mav.maternal_record_id = mhr.maternal_record_id
            JOIN person p ON mhr.person_id = p.person_id
            LEFT JOIN bmi_status bs ON mhr.bmi_status_id = bs.bmi_status_id
            WHERE DATE_PART('year', mav.visit_date) = %s
              AND DATE_PART('month', mav.visit_date) = %s
              AND mhr.is_transferred = false
        ),
        risk_summary AS (
            SELECT 
                COUNT(DISTINCT mav.maternal_record_id) AS total_mothers,
                COUNT(CASE WHEN mav.bmi_status_id = 1 THEN 1 END) AS underweight_count,
                COUNT(CASE WHEN DATE_PART('year', AGE(mav.visit_date, p.birthdate)) < 18 THEN 1 END) AS teen_pregnancy_count,
                COUNT(CASE WHEN oh.has_diabetes = true THEN 1 END) AS diabetes_count,
                COUNT(CASE WHEN oh.num_abortion > 0 THEN 1 END) AS prior_abortion_count,
                COUNT(CASE WHEN oh.num_stillbirth > 0 THEN 1 END) AS prior_stillbirth_count,
                COUNT(CASE WHEN anr.bp_systolic >= 140 OR anr.bp_diastolic >= 90 THEN 1 END) AS hypertension_count,
                ROUND(COUNT(CASE WHEN mav.bmi_status_id = 1 THEN 1 END)::numeric / NULLIF(COUNT(DISTINCT mav.maternal_record_id), 0) * 100, 2) AS underweight_pct,
                ROUND(COUNT(CASE WHEN DATE_PART('year', AGE(mav.visit_date, p.birthdate)) < 18 THEN 1 END)::numeric / NULLIF(COUNT(DISTINCT mav.maternal_record_id), 0) * 100, 2) AS teen_pregnancy_pct
            FROM monthly_anc_visits mav
            LEFT JOIN person p ON mav.person_id = p.person_id
            LEFT JOIN obstetric_history oh ON mav.maternal_record_id = oh.maternal_record_id
            LEFT JOIN maternal_anc_row anr ON mav.anc_visit_id = anr.anc_visit_id
        ),
        risk_category_breakdown AS (
            SELECT 
                rc.risk_category_name,
                COUNT(DISTINCT rr.maternal_record_id) AS mothers_affected,
                ROUND(COUNT(DISTINCT rr.maternal_record_id)::numeric / 
                          NULLIF((SELECT COUNT(DISTINCT maternal_record_id) FROM monthly_anc_visits), 0) * 100, 2) AS percentage
            FROM risk_response rr
            JOIN risk_category rc ON rr.risk_category_id = rc.risk_category_id
            WHERE rr.maternal_record_id IN (SELECT maternal_record_id FROM monthly_anc_visits)
            GROUP BY rc.risk_category_name
            ORDER BY mothers_affected DESC
        ),
        high_risk_mothers AS (
            SELECT 
                mav.maternal_record_id,
                p.first_name || ' ' || p.last_name AS mother_name,
                mav.bmi_status_name,
                DATE_PART('year', AGE(mav.visit_date, p.birthdate)) AS age,
                STRING_AGG(DISTINCT rc.risk_category_name, ', ') AS risk_categories,
                COUNT(DISTINCT rr.risk_response_id) AS risk_score
            FROM monthly_anc_visits mav
            JOIN person p ON mav.person_id = p.person_id
            LEFT JOIN risk_response rr ON mav.maternal_record_id = rr.maternal_record_id
            LEFT JOIN risk_category rc ON rr.risk_category_id = rc.risk_category_id
            GROUP BY mav.maternal_record_id, p.first_name, p.last_name, mav.bmi_status_name, p.birthdate, mav.visit_date
            HAVING COUNT(DISTINCT rr.risk_response_id) >= 2
            ORDER BY risk_score DESC
        )
        SELECT 
            (SELECT row_to_json(rs) FROM risk_summary rs) AS risk_summary,
            (SELECT json_agg(rcb) FROM risk_category_breakdown rcb) AS risk_category_breakdown,
            (SELECT json_agg(hrm) FROM high_risk_mothers hrm) AS high_risk_mothers
        """
        
        result = self._db.execute_query_to_dict(query, (year, month))
        return result[0] if result else {}

    def get_monthly_immunization_supplement_adherence(self, year: int, month: int) -> Dict[str, Any]:
        """
        Monthly Immunization & Supplement Adherence Matrix
        - Tracks vitamins, TT shots, iron/folate adherence
        - KPIs: received vs. pending doses, drop-off rates
        """
        query = """
        WITH monthly_mothers AS (
            SELECT DISTINCT
                mhr.maternal_record_id,
                p.first_name || ' ' || p.last_name AS mother_name
            FROM maternal_health_record mhr
            JOIN person p ON mhr.person_id = p.person_id
            WHERE mhr.is_transferred = false
        ),
        tt_vaccine_status AS (
            SELECT 
                tt.tt_type_name,
                COUNT(DISTINCT ttv.maternal_record_id) AS mothers_received,
                ROUND(COUNT(DISTINCT ttv.maternal_record_id)::numeric / 
                        NULLIF((SELECT COUNT(*) FROM monthly_mothers), 0) * 100, 2) AS coverage_pct
            FROM tt_type tt
            LEFT JOIN tt_vaccine_record ttv ON tt.tt_type_id = ttv.tt_type_id
                AND DATE_PART('year', ttv.date_given) = %s
                AND DATE_PART('month', ttv.date_given) = %s
            GROUP BY tt.tt_type_name
            ORDER BY tt.tt_type_name
        ),
        micronutrient_summary AS (
            SELECT 
                COUNT(DISTINCT CASE WHEN iron_start_date IS NOT NULL THEN maternal_record_id END) AS iron_started,
                COUNT(DISTINCT CASE WHEN iron_end_date IS NOT NULL THEN maternal_record_id END) AS iron_completed,
                COUNT(DISTINCT CASE WHEN deworming_given_date IS NOT NULL THEN maternal_record_id END) AS deworming_given,
                ROUND(COUNT(DISTINCT CASE WHEN iron_end_date IS NOT NULL THEN maternal_record_id END)::numeric / 
                        NULLIF(COUNT(DISTINCT CASE WHEN iron_start_date IS NOT NULL THEN maternal_record_id END), 0) * 100, 2) AS iron_completion_rate
            FROM micronutrients
            WHERE (DATE_PART('year', iron_start_date) = %s AND DATE_PART('month', iron_start_date) = %s)
               OR (DATE_PART('year', deworming_given_date) = %s AND DATE_PART('month', deworming_given_date) = %s)
        ),
        adherence_by_mother AS (
            SELECT 
                mm.maternal_record_id,
                mm.mother_name,
                COUNT(DISTINCT ttv.tt_id) AS tt_doses_received,
                CASE WHEN mic.iron_start_date IS NOT NULL THEN 'Started' ELSE 'Not Started' END AS iron_status,
                CASE WHEN mic.deworming_given_date IS NOT NULL THEN 'Given' ELSE 'Pending' END AS deworming_status,
                CASE 
                    WHEN COUNT(DISTINCT ttv.tt_id) = 0 AND mic.iron_start_date IS NULL THEN 'High Risk'
                    WHEN COUNT(DISTINCT ttv.tt_id) <= 1 OR mic.iron_end_date IS NULL THEN 'Moderate Risk'
                    ELSE 'Compliant'
                END AS adherence_level
            FROM monthly_mothers mm
            LEFT JOIN tt_vaccine_record ttv ON mm.maternal_record_id = ttv.maternal_record_id
                AND DATE_PART('year', ttv.date_given) = %s
                AND DATE_PART('month', ttv.date_given) = %s
            LEFT JOIN micronutrients mic ON mm.maternal_record_id = mic.maternal_record_id
            GROUP BY mm.maternal_record_id, mm.mother_name, mic.iron_start_date, mic.iron_end_date, mic.deworming_given_date
            ORDER BY 
                CASE 
                    WHEN COUNT(DISTINCT ttv.tt_id) = 0 AND mic.iron_start_date IS NULL THEN 1
                    WHEN COUNT(DISTINCT ttv.tt_id) <= 1 OR mic.iron_end_date IS NULL THEN 2
                    ELSE 3
                END
        )
        SELECT 
            (SELECT json_agg(tts) FROM tt_vaccine_status tts) AS tt_vaccine_status,
            (SELECT row_to_json(ms) FROM micronutrient_summary ms) AS micronutrient_summary,
            (SELECT json_agg(abm) FROM adherence_by_mother abm) AS adherence_by_mother
        """
        
        result = self._db.execute_query_to_dict(
            query, 
            (year, month, year, month, year, month, year, month)
        )
        return result[0] if result else {}

    # ===== TRIMESTER REPORTS =====
    
    def get_trimester_health_outcome_trajectory(self, year: int, trimester: int) -> Dict[str, Any]:
        """
        Trimester Health Outcome Trajectory
        - Reviews progression from Trimester 1 → 2 → 3
        - KPIs: weight gain pattern, BP stability, fetal assessments
        """
        query = """
        WITH trimester_visits AS (
            SELECT 
                mav.maternal_record_id,
                mav.anc_visit_id,
                mav.trimester_stage_id,
                ts.trimester_stage_name,
                anr.weight_kg,
                anr.bp_systolic,
                anr.bp_diastolic,
                anr.aog_weeks,
                anr.aog_days,
                anr.anc_date,
                mhr.weight AS baseline_weight,
                mhr.height
            FROM maternal_anc_visit mav
            JOIN maternal_health_record mhr ON mav.maternal_record_id = mhr.maternal_record_id
            JOIN trimester_stage ts ON mav.trimester_stage_id = ts.trimester_stage_id
            LEFT JOIN maternal_anc_row anr ON mav.anc_visit_id = anr.anc_visit_id
            WHERE DATE_PART('year', mav.visit_date) = %s
              AND mav.trimester_stage_id = %s
              AND mhr.is_transferred = false
        ),
        weight_trajectory AS (
            SELECT 
                maternal_record_id,
                COUNT(*) AS visit_count,
                ROUND(AVG(weight_kg)::numeric, 2) AS avg_weight,
                ROUND(MIN(weight_kg), 2) AS min_weight,
                ROUND(MAX(weight_kg), 2) AS max_weight,
                ROUND(MAX(weight_kg) - MIN(weight_kg), 2) AS weight_gain,
                ROUND(AVG(baseline_weight)::numeric, 2) AS baseline_weight,
                CASE 
                    WHEN MAX(weight_kg) - MIN(baseline_weight) < 5 THEN 'Low Gain'
                    WHEN MAX(weight_kg) - MIN(baseline_weight) > 18 THEN 'High Gain'
                    ELSE 'Normal'
                END AS gain_status
            FROM trimester_visits
            WHERE weight_kg IS NOT NULL
            GROUP BY maternal_record_id
        ),
        bp_stability AS (
            SELECT 
                maternal_record_id,
                ROUND(AVG(bp_systolic)::numeric, 2) AS avg_systolic,
                ROUND(AVG(bp_diastolic)::numeric, 2) AS avg_diastolic,
                MAX(bp_systolic) AS max_systolic,
                MAX(bp_diastolic) AS max_diastolic,
                COUNT(CASE WHEN bp_systolic >= 140 OR bp_diastolic >= 90 THEN 1 END) AS hypertensive_readings,
                CASE 
                    WHEN MAX(bp_systolic) >= 140 OR MAX(bp_diastolic) >= 90 THEN 'At Risk'
                    ELSE 'Stable'
                END AS bp_status
            FROM trimester_visits
            WHERE bp_systolic IS NOT NULL AND bp_diastolic IS NOT NULL
            GROUP BY maternal_record_id
        ),
        mother_trajectory AS (
            SELECT 
                tv.maternal_record_id,
                p.first_name || ' ' || p.last_name AS mother_name,
                tv.trimester_stage_name,
                wt.weight_gain,
                wt.gain_status,
                bp.avg_systolic,
                bp.avg_diastolic,
                bp.bp_status,
                COUNT(DISTINCT tv.anc_visit_id) AS visits_this_trimester
            FROM trimester_visits tv
            JOIN maternal_health_record mhr ON tv.maternal_record_id = mhr.maternal_record_id
            JOIN person p ON mhr.person_id = p.person_id
            LEFT JOIN weight_trajectory wt ON tv.maternal_record_id = wt.maternal_record_id
            LEFT JOIN bp_stability bp ON tv.maternal_record_id = bp.maternal_record_id
            GROUP BY tv.maternal_record_id, p.first_name, p.last_name, tv.trimester_stage_name, 
                     wt.weight_gain, wt.gain_status, bp.avg_systolic, bp.avg_diastolic, bp.bp_status
        )
        SELECT 
            (SELECT json_agg(wt) FROM weight_trajectory wt) AS weight_trajectory,
            (SELECT json_agg(bp) FROM bp_stability bp) AS bp_stability,
            (SELECT json_agg(mt) FROM mother_trajectory mt) AS mother_trajectory
        """
        
        result = self._db.execute_query_to_dict(query, (year, trimester))
        return result[0] if result else {}

    def get_trimester_complication_referral_analytics(self, year: int, trimester: int) -> Dict[str, Any]:
        """
        Trimester Complication & Referral Analytics
        - Drills into cases requiring escalation
        - KPIs: referrals, complication types, response times
        """
        query = """
        WITH trimester_visits AS (
            SELECT 
                mav.anc_visit_id,
                mav.maternal_record_id,
                mav.visit_date,
                mav.trimester_stage_id,
                ts.trimester_stage_name
            FROM maternal_anc_visit mav
            JOIN trimester_stage ts ON mav.trimester_stage_id = ts.trimester_stage_id
            WHERE DATE_PART('year', mav.visit_date) = %s
              AND mav.trimester_stage_id = %s
        ),
        complications AS (
            SELECT 
                mc.maternal_record_id,
                mc.anc_visit_id,
                ci.checklist_name AS complication_type,
                tv.trimester_stage_name
            FROM maternal_checklist mc
            JOIN checklist_item ci ON mc.checklist_item_id = ci.checklist_item_id
            JOIN trimester_visits tv ON mc.anc_visit_id = tv.anc_visit_id
        ),
        complication_summary AS (
            SELECT 
                complication_type,
                COUNT(*) AS occurrence_count,
                COUNT(DISTINCT maternal_record_id) AS mothers_affected,
                ROUND(COUNT(DISTINCT maternal_record_id)::numeric / 
                        NULLIF((SELECT COUNT(DISTINCT maternal_record_id) FROM trimester_visits), 0) * 100, 2) AS prevalence_pct
            FROM complications
            GROUP BY complication_type
            ORDER BY occurrence_count DESC
        ),
        medical_complications AS (
            SELECT 
                mh.maternal_record_id,
                p.first_name || ' ' || p.last_name AS mother_name,
                mh.previous_illness,
                mh.previous_hospitalization,
                mh.previous_preg_complication,
                tv.trimester_stage_name
            FROM medical_history mh
            JOIN maternal_health_record mhr ON mh.maternal_record_id = mhr.maternal_record_id
            JOIN person p ON mhr.person_id = p.person_id
            JOIN trimester_visits tv ON mh.anc_visit_id = tv.anc_visit_id
            WHERE mh.previous_preg_complication IS NOT NULL 
              AND mh.previous_preg_complication != 'N/A'
        ),
        risk_referrals AS (
            SELECT 
                rr.maternal_record_id,
                p.first_name || ' ' || p.last_name AS mother_name,
                rc.risk_category_name,
                COUNT(DISTINCT rr.risk_response_id) AS risk_count,
                tv.trimester_stage_name
            FROM risk_response rr
            JOIN risk_category rc ON rr.risk_category_id = rc.risk_category_id
            JOIN maternal_health_record mhr ON rr.maternal_record_id = mhr.maternal_record_id
            JOIN person p ON mhr.person_id = p.person_id
            JOIN trimester_visits tv ON rr.anc_visit_id = tv.anc_visit_id
            GROUP BY rr.maternal_record_id, p.first_name, p.last_name, rc.risk_category_name, tv.trimester_stage_name
            HAVING COUNT(DISTINCT rr.risk_response_id) >= 1
        )
        SELECT 
            (SELECT json_agg(cs) FROM complication_summary cs) AS complication_summary,
            (SELECT json_agg(mc) FROM medical_complications mc) AS medical_complications,
            (SELECT json_agg(rr) FROM risk_referrals rr) AS risk_referrals
        """
        
        result = self._db.execute_query_to_dict(query, (year, trimester))
        return result[0] if result else {}

    def get_trimester_service_utilization(self, year: int, trimester: int) -> Dict[str, Any]:
        """
        Trimester Service Utilization Report
        - Evaluates service uptake: prenatal visits, nutrition counseling, lab use
        - KPIs: visits per trimester, % completing all mandated services
        """
        query = """
        WITH trimester_visits AS (
            SELECT 
                mav.maternal_record_id,
                mav.anc_visit_id,
                mav.visit_date,
                ts.trimester_stage_name
            FROM maternal_anc_visit mav
            JOIN trimester_stage ts ON mav.trimester_stage_id = ts.trimester_stage_id
            WHERE DATE_PART('year', mav.visit_date) = %s
              AND mav.trimester_stage_id = %s
        ),
        visit_counts AS (
            SELECT 
                COUNT(DISTINCT maternal_record_id) AS total_mothers,
                SUM(visits_per_mother) AS total_visits,
                ROUND(AVG(visits_per_mother)::numeric, 2) AS avg_visits_per_mother
            FROM (
                SELECT maternal_record_id, COUNT(*) AS visits_per_mother
                FROM trimester_visits
                GROUP BY maternal_record_id
            ) sub
        ),
        lab_utilization AS (
            SELECT 
                COUNT(DISTINCT lr.maternal_record_id) AS mothers_with_labs,
                COUNT(DISTINCT lr.lab_result_id) AS total_lab_tests,
                ROUND(COUNT(DISTINCT lr.maternal_record_id)::numeric / 
                      NULLIF((SELECT COUNT(DISTINCT maternal_record_id) FROM trimester_visits), 0) * 100, 2) AS lab_coverage_pct
            FROM lab_result lr
            WHERE lr.anc_visit_id IN (SELECT anc_visit_id FROM trimester_visits)
        ),
        tt_vaccination_coverage AS (
            SELECT 
                COUNT(DISTINCT ttv.maternal_record_id) AS mothers_vaccinated,
                COUNT(DISTINCT ttv.tt_id) AS total_doses,
                ROUND(COUNT(DISTINCT ttv.maternal_record_id)::numeric / 
                      NULLIF((SELECT COUNT(DISTINCT maternal_record_id) FROM trimester_visits), 0) * 100, 2) AS tt_coverage_pct
            FROM tt_vaccine_record ttv
            WHERE ttv.anc_visit_id IN (SELECT anc_visit_id FROM trimester_visits)
        ),
        micronutrient_coverage AS (
            SELECT 
                COUNT(DISTINCT CASE WHEN iron_start_date IS NOT NULL THEN maternal_record_id END) AS mothers_on_iron,
                COUNT(DISTINCT CASE WHEN deworming_given_date IS NOT NULL THEN maternal_record_id END) AS mothers_dewormed,
                ROUND(COUNT(DISTINCT CASE WHEN iron_start_date IS NOT NULL THEN maternal_record_id END)::numeric / 
                      NULLIF((SELECT COUNT(DISTINCT maternal_record_id) FROM trimester_visits), 0) * 100, 2) AS iron_coverage_pct
            FROM micronutrients
            WHERE maternal_record_id IN (SELECT maternal_record_id FROM trimester_visits)
        ),
        service_completeness AS (
            SELECT 
                tv.maternal_record_id,
                p.first_name || ' ' || p.last_name AS mother_name,
                COUNT(DISTINCT tv.anc_visit_id) AS visits,
                CASE WHEN EXISTS(SELECT 1 FROM lab_result lr WHERE lr.maternal_record_id = tv.maternal_record_id AND lr.anc_visit_id IN (SELECT anc_visit_id FROM trimester_visits)) THEN 1 ELSE 0 END AS has_lab,
                CASE WHEN EXISTS(SELECT 1 FROM tt_vaccine_record ttv WHERE ttv.maternal_record_id = tv.maternal_record_id AND ttv.anc_visit_id IN (SELECT anc_visit_id FROM trimester_visits)) THEN 1 ELSE 0 END AS has_tt,
                CASE WHEN EXISTS(SELECT 1 FROM micronutrients mic WHERE mic.maternal_record_id = tv.maternal_record_id AND mic.iron_start_date IS NOT NULL) THEN 1 ELSE 0 END AS has_iron,
                (CASE WHEN EXISTS(SELECT 1 FROM lab_result lr WHERE lr.maternal_record_id = tv.maternal_record_id AND lr.anc_visit_id IN (SELECT anc_visit_id FROM trimester_visits)) THEN 1 ELSE 0 END +
                 CASE WHEN EXISTS(SELECT 1 FROM tt_vaccine_record ttv WHERE ttv.maternal_record_id = tv.maternal_record_id AND ttv.anc_visit_id IN (SELECT anc_visit_id FROM trimester_visits)) THEN 1 ELSE 0 END +
                 CASE WHEN EXISTS(SELECT 1 FROM micronutrients mic WHERE mic.maternal_record_id = tv.maternal_record_id AND mic.iron_start_date IS NOT NULL) THEN 1 ELSE 0 END) AS services_completed
            FROM trimester_visits tv
            JOIN maternal_health_record mhr ON tv.maternal_record_id = mhr.maternal_record_id
            JOIN person p ON mhr.person_id = p.person_id
            GROUP BY tv.maternal_record_id, p.first_name, p.last_name
            ORDER BY services_completed DESC
        )
        SELECT 
            (SELECT row_to_json(vc) FROM visit_counts vc) AS visit_counts,
            (SELECT row_to_json(lu) FROM lab_utilization lu) AS lab_utilization,
            (SELECT row_to_json(ttvc) FROM tt_vaccination_coverage ttvc) AS tt_vaccination_coverage,
            (SELECT row_to_json(mc) FROM micronutrient_coverage mc) AS micronutrient_coverage,
            (SELECT json_agg(sc) FROM service_completeness sc) AS service_completeness
        """
        
        result = self._db.execute_query_to_dict(query, (year, trimester))
        return result[0] if result else {}

    # ===== ANNUAL REPORTS =====
    
    def get_annual_maternal_outcome_consolidated(self, year: int) -> Dict[str, Any]:
        """
        Annual Maternal Outcome & Incident Consolidated Report
        - Full-year strategic governance report
        - KPIs: total pregnancies, live births, stillbirths, complications, mortality markers
        """
        query = """
        WITH annual_pregnancies AS (
            SELECT 
                mhr.maternal_record_id,
                mhr.person_id,
                mhr.created_at,
                p.first_name || ' ' || p.last_name AS mother_name,
                DATE_PART('year', AGE(mhr.created_at, p.birthdate)) AS mother_age,
                mhr.bmi_status_id,
                bs.bmi_status_name
            FROM maternal_health_record mhr
            JOIN person p ON mhr.person_id = p.person_id
            LEFT JOIN bmi_status bs ON mhr.bmi_status_id = bs.bmi_status_id
            WHERE DATE_PART('year', mhr.created_at) = %s
              AND mhr.is_transferred = false
        ),
        pregnancy_outcomes AS (
            SELECT 
                COUNT(DISTINCT ap.maternal_record_id) AS total_pregnancies,
                COUNT(DISTINCT CASE WHEN ppi.outcome = 'fullterm' THEN ap.maternal_record_id END) AS live_births,
                COUNT(CASE WHEN oh.num_stillbirth > 0 THEN 1 END) AS stillbirths,
                COUNT(CASE WHEN oh.num_abortion > 0 THEN 1 END) AS abortions,
                ROUND(AVG(ap.mother_age)::numeric, 1) AS avg_mother_age,
                COUNT(CASE WHEN ap.mother_age < 18 THEN 1 END) AS teen_pregnancies,
                COUNT(CASE WHEN ap.bmi_status_id = 1 THEN 1 END) AS underweight_mothers
            FROM annual_pregnancies ap
            LEFT JOIN previous_pregnancy_info ppi ON ap.maternal_record_id = ppi.maternal_record_id
            LEFT JOIN obstetric_history oh ON ap.maternal_record_id = oh.maternal_record_id
        ),
        delivery_type_breakdown AS (
            SELECT 
                dt.delivery_type_name,
                COUNT(*) AS delivery_count,
                ROUND(COUNT(*)::numeric / NULLIF((SELECT COUNT(*) FROM previous_pregnancy_info WHERE DATE_PART('year', date_of_deliveries) = %s), 0) * 100, 2) AS percentage
            FROM previous_pregnancy_info ppi
            JOIN delivery_type dt ON ppi.delivery_type_id = dt.delivery_type_id
            WHERE DATE_PART('year', ppi.date_of_deliveries) = %s
            GROUP BY dt.delivery_type_name
        ),
        complications_summary AS (
            SELECT 
                ci.checklist_name AS complication_type,
                COUNT(DISTINCT mc.maternal_record_id) AS mothers_affected,
                COUNT(*) AS total_incidents
            FROM maternal_checklist mc
            JOIN checklist_item ci ON mc.checklist_item_id = ci.checklist_item_id
            WHERE mc.maternal_record_id IN (SELECT maternal_record_id FROM annual_pregnancies)
            GROUP BY ci.checklist_name
            ORDER BY total_incidents DESC
        ),
        risk_distribution AS (
            SELECT 
                rc.risk_category_name,
                COUNT(DISTINCT rr.maternal_record_id) AS mothers_at_risk,
                ROUND(COUNT(DISTINCT rr.maternal_record_id)::numeric / 
                        NULLIF((SELECT COUNT(*) FROM annual_pregnancies), 0) * 100, 2) AS risk_percentage
            FROM risk_response rr
            JOIN risk_category rc ON rr.risk_category_id = rc.risk_category_id
            WHERE rr.maternal_record_id IN (SELECT maternal_record_id FROM annual_pregnancies)
            GROUP BY rc.risk_category_name
        )
        SELECT 
            (SELECT row_to_json(po) FROM pregnancy_outcomes po) AS pregnancy_outcomes,
            (SELECT json_agg(dtb) FROM delivery_type_breakdown dtb) AS delivery_type_breakdown,
            (SELECT json_agg(cs) FROM complications_summary cs) AS complications_summary,
            (SELECT json_agg(rd) FROM risk_distribution rd) AS risk_distribution
        """
        
        result = self._db.execute_query_to_dict(query, (year, year, year))
        return result[0] if result else {}

    def get_annual_coverage_scorecard(self, year: int) -> Dict[str, Any]:
        """
        Annual Barangay Maternal Health Coverage Scorecard
        - Measures how many pregnant women reached DOH-recommended standards
        - KPIs: 4+ prenatal visits, TT doses, nutrition support, facility-based delivery
        """
        query = """
        WITH annual_mothers AS (
            SELECT 
                mhr.maternal_record_id,
                p.first_name || ' ' || p.last_name AS mother_name,
                mhr.family_id
            FROM maternal_health_record mhr
            JOIN person p ON mhr.person_id = p.person_id
            WHERE DATE_PART('year', mhr.created_at) = %s
              AND mhr.is_transferred = false
        ),
        prenatal_visit_compliance AS (
            SELECT 
                am.maternal_record_id,
                COUNT(DISTINCT mav.anc_visit_id) AS total_visits,
                CASE WHEN COUNT(DISTINCT mav.anc_visit_id) >= 4 THEN 1 ELSE 0 END AS meets_4plus_visits
            FROM annual_mothers am
            LEFT JOIN maternal_anc_visit mav ON am.maternal_record_id = mav.maternal_record_id
            WHERE DATE_PART('year', mav.visit_date) = %s
            GROUP BY am.maternal_record_id
        ),
        tt_compliance AS (
            SELECT 
                am.maternal_record_id,
                COUNT(DISTINCT ttv.tt_id) AS tt_doses_received,
                CASE WHEN COUNT(DISTINCT ttv.tt_id) >= 2 THEN 1 ELSE 0 END AS meets_tt_requirement
            FROM annual_mothers am
            LEFT JOIN tt_vaccine_record ttv ON am.maternal_record_id = ttv.maternal_record_id
            WHERE DATE_PART('year', ttv.date_given) = %s
            GROUP BY am.maternal_record_id
        ),
        nutrition_compliance AS (
            SELECT 
                am.maternal_record_id,
                CASE WHEN mic.iron_start_date IS NOT NULL THEN 1 ELSE 0 END AS received_iron,
                CASE WHEN mic.deworming_given_date IS NOT NULL THEN 1 ELSE 0 END AS received_deworming
            FROM annual_mothers am
            LEFT JOIN micronutrients mic ON am.maternal_record_id = mic.maternal_record_id
        ),
        overall_scorecard AS (
            SELECT 
                COUNT(*) AS total_mothers,
                SUM(pvc.meets_4plus_visits) AS mothers_4plus_visits,
                SUM(ttc.meets_tt_requirement) AS mothers_tt_compliant,
                SUM(nc.received_iron) AS mothers_on_iron,
                SUM(nc.received_deworming) AS mothers_dewormed,
                ROUND(SUM(pvc.meets_4plus_visits)::numeric / NULLIF(COUNT(*), 0) * 100, 2) AS prenatal_compliance_pct,
                ROUND(SUM(ttc.meets_tt_requirement)::numeric / NULLIF(COUNT(*), 0) * 100, 2) AS tt_compliance_pct,
                ROUND(SUM(nc.received_iron)::numeric / NULLIF(COUNT(*), 0) * 100, 2) AS iron_coverage_pct,
                ROUND(SUM(nc.received_deworming)::numeric / NULLIF(COUNT(*), 0) * 100, 2) AS deworming_coverage_pct
            FROM annual_mothers am
            LEFT JOIN prenatal_visit_compliance pvc ON am.maternal_record_id = pvc.maternal_record_id
            LEFT JOIN tt_compliance ttc ON am.maternal_record_id = ttc.maternal_record_id
            LEFT JOIN nutrition_compliance nc ON am.maternal_record_id = nc.maternal_record_id
        ),
        mother_scorecard AS (
            SELECT 
                am.maternal_record_id,
                am.mother_name,
                COALESCE(pvc.total_visits, 0) AS total_visits,
                pvc.meets_4plus_visits,
                COALESCE(ttc.tt_doses_received, 0) AS tt_doses,
                ttc.meets_tt_requirement,
                nc.received_iron,
                nc.received_deworming,
                (COALESCE(pvc.meets_4plus_visits, 0) + COALESCE(ttc.meets_tt_requirement, 0) + 
                 COALESCE(nc.received_iron, 0) + COALESCE(nc.received_deworming, 0)) AS compliance_score,
                CASE 
                    WHEN (COALESCE(pvc.meets_4plus_visits, 0) + COALESCE(ttc.meets_tt_requirement, 0) + 
                          COALESCE(nc.received_iron, 0) + COALESCE(nc.received_deworming, 0)) >= 3 THEN 'Excellent'
                    WHEN (COALESCE(pvc.meets_4plus_visits, 0) + COALESCE(ttc.meets_tt_requirement, 0) + 
                          COALESCE(nc.received_iron, 0) + COALESCE(nc.received_deworming, 0)) = 2 THEN 'Good'
                    ELSE 'Needs Improvement'
                END AS compliance_level
            FROM annual_mothers am
            LEFT JOIN prenatal_visit_compliance pvc ON am.maternal_record_id = pvc.maternal_record_id
            LEFT JOIN tt_compliance ttc ON am.maternal_record_id = ttc.maternal_record_id
            LEFT JOIN nutrition_compliance nc ON am.maternal_record_id = nc.maternal_record_id
            ORDER BY compliance_score DESC
        )
        SELECT 
            (SELECT row_to_json(os) FROM overall_scorecard os) AS overall_scorecard,
            (SELECT json_agg(ms) FROM mother_scorecard ms) AS mother_scorecard
        """
        
        result = self._db.execute_query_to_dict(query, (year, year, year))
        return result[0] if result else {}

    def get_annual_trend_analysis(self, year: int) -> Dict[str, Any]:
        """
        Annual Trend Analysis & Forecasting Model
        - Uses yearlong data to analyze patterns and project needs
        - KPIs: rising risk factors, demographic shifts, expected pregnancies
        """
        query = """
        WITH monthly_aggregates AS (
            SELECT 
                DATE_PART('month', mhr.created_at) AS month,
                COUNT(DISTINCT mhr.maternal_record_id) AS new_pregnancies,
                COUNT(CASE WHEN mhr.bmi_status_id = 1 THEN 1 END) AS underweight_cases,
                COUNT(CASE WHEN DATE_PART('year', AGE(mhr.created_at, p.birthdate)) < 18 THEN 1 END) AS teen_pregnancies
            FROM maternal_health_record mhr
            JOIN person p ON mhr.person_id = p.person_id
            WHERE DATE_PART('year', mhr.created_at) = %s
              AND mhr.is_transferred = false
            GROUP BY DATE_PART('month', mhr.created_at)
            ORDER BY month
        ),
        risk_trends AS (
            SELECT 
                DATE_PART('month', mav.visit_date) AS month,
                COUNT(DISTINCT rr.maternal_record_id) AS mothers_at_risk,
                COUNT(DISTINCT CASE WHEN rc.risk_category_id = 1 THEN rr.maternal_record_id END) AS obstetric_risks,
                COUNT(DISTINCT CASE WHEN rc.risk_category_id = 2 THEN rr.maternal_record_id END) AS medical_risks
            FROM maternal_anc_visit mav
            LEFT JOIN risk_response rr ON mav.anc_visit_id = rr.anc_visit_id
            LEFT JOIN risk_category rc ON rr.risk_category_id = rc.risk_category_id
            WHERE DATE_PART('year', mav.visit_date) = %s
            GROUP BY DATE_PART('month', mav.visit_date)
            ORDER BY month
        ),
        service_trends AS (
            SELECT 
                DATE_PART('month', mav.visit_date) AS month,
                COUNT(DISTINCT mav.anc_visit_id) AS total_visits,
                COUNT(DISTINCT ttv.tt_id) AS tt_doses_given,
                COUNT(DISTINCT lr.lab_result_id) AS lab_tests_conducted
            FROM maternal_anc_visit mav
            LEFT JOIN tt_vaccine_record ttv ON mav.anc_visit_id = ttv.anc_visit_id
            LEFT JOIN lab_result lr ON mav.anc_visit_id = lr.anc_visit_id
            WHERE DATE_PART('year', mav.visit_date) = %s
            GROUP BY DATE_PART('month', mav.visit_date)
            ORDER BY month
        ),
        yearly_summary AS (
            SELECT 
                COUNT(DISTINCT mhr.maternal_record_id) AS total_pregnancies_year,
                ROUND(AVG(monthly_counts.monthly_avg)::numeric, 2) AS avg_pregnancies_per_month,
                MAX(monthly_counts.monthly_max) AS peak_month_pregnancies,
                MIN(monthly_counts.monthly_min) AS lowest_month_pregnancies
            FROM maternal_health_record mhr
            CROSS JOIN (
                SELECT 
                    AVG(pregnancy_count) AS monthly_avg,
                    MAX(pregnancy_count) AS monthly_max,
                    MIN(pregnancy_count) AS monthly_min
                FROM (
                    SELECT DATE_PART('month', created_at) AS month, COUNT(*) AS pregnancy_count
                    FROM maternal_health_record
                    WHERE DATE_PART('year', created_at) = %s
                    GROUP BY DATE_PART('month', created_at)
                ) monthly_data
            ) monthly_counts
            WHERE DATE_PART('year', mhr.created_at) = %s
        ),
        forecast_projection AS (
            SELECT 
                'Next Year Estimate' AS forecast_type,
                ROUND((SELECT total_pregnancies_year FROM yearly_summary) * 1.05, 0) AS projected_pregnancies,
                ROUND((SELECT total_pregnancies_year FROM yearly_summary) * 0.15, 0) AS estimated_high_risk_cases,
                ROUND((SELECT total_pregnancies_year FROM yearly_summary) * 4.5, 0) AS estimated_total_visits
        )
        SELECT 
            (SELECT json_agg(ma) FROM monthly_aggregates ma) AS monthly_aggregates,
            (SELECT json_agg(rt) FROM risk_trends rt) AS risk_trends,
            (SELECT json_agg(st) FROM service_trends st) AS service_trends,
            (SELECT row_to_json(ys) FROM yearly_summary ys) AS yearly_summary,
            (SELECT row_to_json(fp) FROM forecast_projection fp) AS forecast_projection
        """
        
        result = self._db.execute_query_to_dict(query, (year, year, year, year, year))
        return result[0] if result else {}
        
    