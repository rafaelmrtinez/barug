from typing import Dict, List, Any, Optional
from datetime import date
from src.infra.contracts.connection_adapter import IConnectionAdapter


class ChildReportsQuery:
    def __init__(self, db_connection: IConnectionAdapter):
        self.db_connection = db_connection

    def get_monthly_immunization_coverage(self, year: int, month: int) -> Dict[str, Any]:
        """
        Monthly Immunization Coverage & Compliance Report
        - % of children who received vaccines on time
        - Missed / delayed immunizations
        - Immunization types with low coverage
        - Children repeatedly falling behind schedule
        """
        query = """
        WITH immunization_schedule AS (
            -- Expected immunization schedule based on child's birth date
            SELECT 
                chr.child_record_id,
                p.first_name || ' ' || p.last_name AS child_name,
                p.birthdate,
                DATE_PART('year', AGE(MAKE_DATE(%s, %s, 1), p.birthdate)) * 12 + 
                DATE_PART('month', AGE(MAKE_DATE(%s, %s, 1), p.birthdate)) AS age_months
            FROM child_health_record chr
            JOIN person p ON chr.person_id = p.person_id
            WHERE chr.is_transferred = false
        ),
        actual_immunizations AS (
            SELECT 
                ci.child_record_id,
                ci.immunization_type_id,
                ci.date_given,
                it.immunization_type_name,
                DATE_PART('month', ci.date_given) AS given_month,
                DATE_PART('year', ci.date_given) AS given_year
            FROM child_immunization ci
            LEFT JOIN immunization_type it ON ci.immunization_type_id = it.immunization_type_id
            WHERE DATE_PART('year', ci.date_given) = %s
              AND DATE_PART('month', ci.date_given) = %s
        ),
        coverage_stats AS (
            SELECT 
                COUNT(DISTINCT isch.child_record_id) AS total_children,
                COUNT(DISTINCT ai.child_record_id) AS children_vaccinated,
                ROUND(COUNT(DISTINCT ai.child_record_id)::numeric / NULLIF(COUNT(DISTINCT isch.child_record_id), 0) * 100, 2) AS coverage_percentage
            FROM immunization_schedule isch
            LEFT JOIN actual_immunizations ai ON isch.child_record_id = ai.child_record_id
        ),
        immunization_type_coverage AS (
            SELECT 
                COALESCE(it.immunization_type_name, 'Unknown') AS vaccine_type,
                COUNT(*) AS doses_given,
                COUNT(DISTINCT ai.child_record_id) AS children_receiving
            FROM immunization_type it
            LEFT JOIN actual_immunizations ai ON it.immunization_type_id = ai.immunization_type_id
            GROUP BY it.immunization_type_name
            ORDER BY doses_given ASC
        ),
        repeat_offenders AS (
            SELECT 
                chr.child_record_id,
                p.first_name || ' ' || p.last_name AS child_name,
                COUNT(DISTINCT cvs.child_visit_schedule_id) AS missed_visits,
                STRING_AGG(DISTINCT it.immunization_type_name, ', ') AS missing_vaccines
            FROM child_health_record chr
            JOIN person p ON chr.person_id = p.person_id
            LEFT JOIN child_visit_schedule cvs ON chr.child_record_id = cvs.child_record_id 
                AND cvs.status_id = 3 -- missed/incomplete
            LEFT JOIN child_immunization ci ON chr.child_record_id = ci.child_record_id
            LEFT JOIN immunization_type it ON ci.immunization_type_id = it.immunization_type_id
            WHERE chr.is_transferred = false
            GROUP BY chr.child_record_id, p.first_name, p.last_name
            HAVING COUNT(DISTINCT cvs.child_visit_schedule_id) >= 2
            ORDER BY missed_visits DESC
        )
        SELECT 
            (SELECT row_to_json(cs) FROM coverage_stats cs) AS coverage_summary,
            (SELECT json_agg(itc) FROM immunization_type_coverage itc) AS type_coverage,
            (SELECT json_agg(ro) FROM repeat_offenders ro) AS repeat_offenders
        """
        
        result = self.db_connection.execute_query_to_dict(
            query, 
            (year, month, year, month, year, month)
        )
        return result[0] if result else {}

    def get_monthly_visit_completion(self, year: int, month: int) -> Dict[str, Any]:
        """
        Monthly Visit Completion & Missed Visit Report
        - Total scheduled vs. completed visits
        - Delayed visits and average delay duration
        - Households repeatedly missing visits
        - Worker-level performance on follow-ups
        """
        query = """
        WITH monthly_visits AS (
            SELECT 
                cvs.child_visit_schedule_id,
                cvs.child_record_id,
                cvs.scheduled_date,
                cvs.date_time_completed,
                cvs.status_id,
                rs.record_status_name AS status_name,
                cvs.marked_completed_by_id,
                CASE 
                    WHEN cvs.date_time_completed IS NOT NULL AND cvs.scheduled_date IS NOT NULL
                    THEN cvs.date_time_completed::date - cvs.scheduled_date
                    ELSE NULL
                END AS delay_days
            FROM child_visit_schedule cvs
            LEFT JOIN record_status rs ON cvs.status_id = rs.record_status_id
            WHERE DATE_PART('year', cvs.scheduled_date) = %s
              AND DATE_PART('month', cvs.scheduled_date) = %s
        ),
        visit_summary AS (
            SELECT 
                COUNT(*) AS total_scheduled,
                COUNT(CASE WHEN status_id = 2 THEN 1 END) AS completed_visits,
                COUNT(CASE WHEN status_id = 3 THEN 1 END) AS missed_visits,
                COUNT(CASE WHEN delay_days > 0 THEN 1 END) AS delayed_visits,
                ROUND(AVG(CASE WHEN delay_days > 0 THEN delay_days END), 2) AS avg_delay_days,
                ROUND(COUNT(CASE WHEN status_id = 2 THEN 1 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) AS completion_rate
            FROM monthly_visits
        ),
        household_performance AS (
            SELECT 
                chr.family_id,
                COUNT(DISTINCT mv.child_visit_schedule_id) AS total_visits,
                COUNT(CASE WHEN mv.status_id = 3 THEN 1 END) AS missed_count,
                ROUND(COUNT(CASE WHEN mv.status_id = 3 THEN 1 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) AS miss_rate
            FROM monthly_visits mv
            JOIN child_health_record chr ON mv.child_record_id = chr.child_record_id
            GROUP BY chr.family_id
            HAVING COUNT(CASE WHEN mv.status_id = 3 THEN 1 END) >= 2
            ORDER BY missed_count DESC
        ),
        worker_performance AS (
            SELECT 
                COALESCE(mv.marked_completed_by_id, cv.recorded_by_id) AS worker_id,
                COALESCE(CAST(COALESCE(mv.marked_completed_by_id, cv.recorded_by_id) AS TEXT), 'Unassigned') AS worker_name,
                COUNT(DISTINCT mv.child_visit_schedule_id) AS visits_handled,
                COUNT(CASE WHEN mv.status_id = 2 THEN 1 END) AS completed,
                ROUND(COUNT(CASE WHEN mv.status_id = 2 THEN 1 END)::numeric / NULLIF(COUNT(*), 0) * 100, 2) AS completion_rate
            FROM monthly_visits mv
            LEFT JOIN child_visit cv ON mv.child_record_id = cv.child_record_id
            GROUP BY worker_id, COALESCE(CAST(COALESCE(mv.marked_completed_by_id, cv.recorded_by_id) AS TEXT), 'Unassigned')
            ORDER BY completion_rate DESC
        )
        SELECT 
            (SELECT row_to_json(vs) FROM visit_summary vs) AS visit_summary,
            (SELECT json_agg(hp) FROM household_performance hp) AS household_performance,
            (SELECT json_agg(wp) FROM worker_performance wp) AS worker_performance
        """
        
        result = self.db_connection.execute_query_to_dict(query, (year, month))
        return result[0] if result else {}

    def get_monthly_growth_nutrition(self, year: int, month: int) -> Dict[str, Any]:
        """
        Monthly Growth & Nutrition Monitoring Report
        - Underweight / stunted / wasted children
        - Temperature or illness trends
        - Growth consistency month-to-month
        - Hotspots per purok / zone
        """
        query = """
        WITH monthly_monitoring AS (
            SELECT 
                cml.child_monitoring_id,
                cml.child_record_id,
                cml.check_date,
                cml.age,
                cml.weight,
                cml.height,
                cml.temperature,
                cml.findings,
                chr.family_id,
                p.birthdate,
                -- WHO Z-score approximations (simplified)
                CASE 
                    WHEN cml.weight < 10 AND cml.age <= 12 THEN 'underweight'
                    WHEN cml.weight < 15 AND cml.age BETWEEN 13 AND 24 THEN 'underweight'
                    WHEN cml.weight < 20 AND cml.age > 24 THEN 'underweight'
                    ELSE 'normal'
                END AS weight_status,
                CASE 
                    WHEN cml.height < 70 AND cml.age <= 12 THEN 'stunted'
                    WHEN cml.height < 80 AND cml.age BETWEEN 13 AND 24 THEN 'stunted'
                    WHEN cml.height < 90 AND cml.age > 24 THEN 'stunted'
                    ELSE 'normal'
                END AS height_status,
                CASE 
                    WHEN cml.temperature >= 38.0 THEN 'fever'
                    WHEN cml.temperature <= 36.0 THEN 'hypothermia'
                    ELSE 'normal'
                END AS temp_status
            FROM child_monitoring_log cml
            JOIN child_health_record chr ON cml.child_record_id = chr.child_record_id
            JOIN person p ON chr.person_id = p.person_id
            WHERE DATE_PART('year', cml.check_date) = %s
              AND DATE_PART('month', cml.check_date) = %s
              AND chr.is_transferred = false
        ),
        nutrition_summary AS (
            SELECT 
                COUNT(DISTINCT child_record_id) AS total_monitored,
                COUNT(CASE WHEN weight_status = 'underweight' THEN 1 END) AS underweight_count,
                COUNT(CASE WHEN height_status = 'stunted' THEN 1 END) AS stunted_count,
                COUNT(CASE WHEN temp_status = 'fever' THEN 1 END) AS fever_cases,
                ROUND(AVG(weight), 2) AS avg_weight,
                ROUND(AVG(height), 2) AS avg_height,
                ROUND(AVG(temperature), 2) AS avg_temperature
            FROM monthly_monitoring
        ),
        growth_consistency AS (
            SELECT 
                cml.child_record_id,
                p.first_name || ' ' || p.last_name AS child_name,
                COUNT(*) AS check_count,
                ROUND(STDDEV(cml.weight), 2) AS weight_variance,
                ROUND(STDDEV(cml.height), 2) AS height_variance,
                CASE 
                    WHEN STDDEV(cml.weight) < 1 THEN 'stable'
                    WHEN STDDEV(cml.weight) BETWEEN 1 AND 2 THEN 'moderate_variance'
                    ELSE 'high_variance'
                END AS growth_pattern
            FROM child_monitoring_log cml
            JOIN child_health_record chr ON cml.child_record_id = chr.child_record_id
            JOIN person p ON chr.person_id = p.person_id
            WHERE cml.check_date >= MAKE_DATE(%s, %s, 1) - INTERVAL '3 months'
              AND cml.check_date < MAKE_DATE(%s, %s, 1) + INTERVAL '1 month'
            GROUP BY cml.child_record_id, p.first_name, p.last_name
            HAVING COUNT(*) >= 2
        ),
        hotspot_analysis AS (
            SELECT 
                chr.family_id AS purok,
                COUNT(DISTINCT mm.child_record_id) AS children_monitored,
                COUNT(CASE WHEN mm.weight_status = 'underweight' THEN 1 END) AS underweight_cases,
                COUNT(CASE WHEN mm.height_status = 'stunted' THEN 1 END) AS stunted_cases,
                ROUND(COUNT(CASE WHEN mm.weight_status = 'underweight' THEN 1 END)::numeric / 
                      NULLIF(COUNT(DISTINCT mm.child_record_id), 0) * 100, 2) AS malnutrition_rate
            FROM monthly_monitoring mm
            JOIN child_health_record chr ON mm.child_record_id = chr.child_record_id
            WHERE chr.family_id IS NOT NULL
            GROUP BY chr.family_id
            ORDER BY malnutrition_rate DESC
        )
        SELECT 
            (SELECT row_to_json(ns) FROM nutrition_summary ns) AS nutrition_summary,
            (SELECT json_agg(gc) FROM growth_consistency gc) AS growth_consistency,
            (SELECT json_agg(ha) FROM hotspot_analysis ha) AS hotspot_analysis
        """
        
        result = self.db_connection.execute_query_to_dict(
            query, 
            (year, month, year, month, year, month)
        )
        return result[0] if result else {}

    def get_annual_screening_risk(self, year: int) -> Dict[str, Any]:
        """
        Annual Screening & Risk Factor Summary
        - Total Low Birth Weight cases
        - Total anemia screenings & supplementation
        - Trends in early-risk populations
        - Comparative month-to-month risk changes
        """
        query = """
        WITH annual_screenings AS (
            SELECT 
                csa.screening_id,
                csa.child_record_id,
                csa.date_assessed,
                csa.birth_weight,
                csa.is_low_birth_weight,
                csa.anemic_seen_date,
                csa.anemic_given_iron_date,
                csa.iron_seen_2_6_mos_date,
                csa.iron_given_2_6_mos_date,
                DATE_PART('month', csa.date_assessed) AS assessment_month,
                chr.family_id,
                p.birthdate
            FROM child_screening_assessment csa
            JOIN child_health_record chr ON csa.child_record_id = chr.child_record_id
            JOIN person p ON chr.person_id = p.person_id
            WHERE DATE_PART('year', COALESCE(csa.date_assessed, chr.created_at::date)) = %s
              AND chr.is_transferred = false
        ),
        risk_summary AS (
            SELECT 
                COUNT(DISTINCT child_record_id) AS total_screenings,
                COUNT(CASE WHEN is_low_birth_weight = true THEN 1 END) AS low_birth_weight_cases,
                COUNT(CASE WHEN anemic_seen_date IS NOT NULL THEN 1 END) AS anemia_screenings,
                COUNT(CASE WHEN anemic_given_iron_date IS NOT NULL THEN 1 END) AS anemia_supplemented,
                COUNT(CASE WHEN iron_seen_2_6_mos_date IS NOT NULL THEN 1 END) AS iron_screenings_2_6mo,
                COUNT(CASE WHEN iron_given_2_6_mos_date IS NOT NULL THEN 1 END) AS iron_supplemented_2_6mo,
                ROUND(AVG(birth_weight), 2) AS avg_birth_weight,
                ROUND(COUNT(CASE WHEN is_low_birth_weight = true THEN 1 END)::numeric / 
                      NULLIF(COUNT(*), 0) * 100, 2) AS lbw_rate
            FROM annual_screenings
        ),
        monthly_trends AS (
            SELECT 
                assessment_month AS month,
                COUNT(DISTINCT child_record_id) AS screenings_count,
                COUNT(CASE WHEN is_low_birth_weight = true THEN 1 END) AS lbw_cases,
                COUNT(CASE WHEN anemic_seen_date IS NOT NULL THEN 1 END) AS anemia_cases,
                ROUND(COUNT(CASE WHEN is_low_birth_weight = true THEN 1 END)::numeric / 
                      NULLIF(COUNT(*), 0) * 100, 2) AS lbw_rate_pct
            FROM annual_screenings
            WHERE assessment_month IS NOT NULL
            GROUP BY assessment_month
            ORDER BY assessment_month
        ),
        early_risk_populations AS (
            SELECT 
                a_scr.child_record_id,
                p.first_name || ' ' || p.last_name AS child_name,
                a_scr.birth_weight,
                a_scr.is_low_birth_weight,
                CASE 
                    WHEN a_scr.anemic_seen_date IS NOT NULL THEN 'anemic'
                    ELSE 'not_anemic'
                END AS anemia_status,
                chr.family_id AS purok
            FROM annual_screenings a_scr
            JOIN child_health_record chr ON a_scr.child_record_id = chr.child_record_id
            JOIN person p ON chr.person_id = p.person_id
            WHERE a_scr.is_low_birth_weight = true 
               OR a_scr.anemic_seen_date IS NOT NULL
            ORDER BY a_scr.birth_weight ASC NULLS LAST
        )
        SELECT 
            (SELECT row_to_json(rs) FROM risk_summary rs) AS risk_summary,
            (SELECT json_agg(mt) FROM monthly_trends mt) AS monthly_trends,
            (SELECT json_agg(erp) FROM early_risk_populations erp) AS early_risk_populations
        """
        
        result = self.db_connection.execute_query_to_dict(query, (year,))
        return result[0] if result else {}

    def get_annual_immunization_performance(self, year: int) -> Dict[str, Any]:
        """
        Annual Immunization Performance Dashboard
        - Full-year coverage by vaccine type
        - Seasonal dips in immunization
        - Year-over-year immunization improvement
        - Barangay's herd-immunity indicators
        """
        query = """
        WITH annual_immunizations AS (
            SELECT 
                ci.child_immunization_id,
                ci.child_record_id,
                ci.date_given,
                ci.immunization_type_id,
                it.immunization_type_name,
                DATE_PART('month', ci.date_given) AS immunization_month,
                DATE_PART('year', ci.date_given) AS immunization_year
            FROM child_immunization ci
            LEFT JOIN immunization_type it ON ci.immunization_type_id = it.immunization_type_id
            WHERE DATE_PART('year', ci.date_given) = %s
        ),
        vaccine_coverage AS (
            SELECT 
                immunization_type_name AS vaccine_name,
                COUNT(*) AS doses_administered,
                COUNT(DISTINCT child_record_id) AS children_immunized,
                ROUND(COUNT(DISTINCT child_record_id)::numeric / 
                      (SELECT COUNT(*) FROM child_health_record WHERE is_transferred = false) * 100, 2) AS coverage_rate
            FROM annual_immunizations
            GROUP BY immunization_type_name
            ORDER BY coverage_rate DESC
        ),
        seasonal_trends AS (
            SELECT 
                immunization_month AS month,
                COUNT(*) AS total_doses,
                COUNT(DISTINCT child_record_id) AS children_immunized,
                STRING_AGG(DISTINCT immunization_type_name, ', ') AS vaccine_types
            FROM annual_immunizations
            GROUP BY immunization_month
            ORDER BY immunization_month
        ),
        yoy_comparison AS (
            SELECT 
                DATE_PART('year', ci.date_given) AS year,
                COUNT(*) AS total_immunizations,
                COUNT(DISTINCT ci.child_record_id) AS children_immunized,
                COUNT(DISTINCT ci.immunization_type_id) AS vaccine_types_used
            FROM child_immunization ci
            WHERE DATE_PART('year', ci.date_given) IN (%s, %s - 1)
            GROUP BY DATE_PART('year', ci.date_given)
            ORDER BY year
        ),
        herd_immunity_estimate AS (
            SELECT 
                it.immunization_type_name AS vaccine_type,
                COUNT(DISTINCT ci.child_record_id) AS immunized_children,
                (SELECT COUNT(*) FROM child_health_record WHERE is_transferred = false) AS total_children,
                ROUND(COUNT(DISTINCT ci.child_record_id)::numeric / 
                      NULLIF((SELECT COUNT(*) FROM child_health_record WHERE is_transferred = false), 0) * 100, 2) AS coverage_percentage,
                CASE 
                    WHEN ROUND(COUNT(DISTINCT ci.child_record_id)::numeric / 
                              NULLIF((SELECT COUNT(*) FROM child_health_record WHERE is_transferred = false), 0) * 100, 2) >= 95 
                    THEN 'excellent'
                    WHEN ROUND(COUNT(DISTINCT ci.child_record_id)::numeric / 
                              NULLIF((SELECT COUNT(*) FROM child_health_record WHERE is_transferred = false), 0) * 100, 2) >= 85 
                    THEN 'good'
                    WHEN ROUND(COUNT(DISTINCT ci.child_record_id)::numeric / 
                              NULLIF((SELECT COUNT(*) FROM child_health_record WHERE is_transferred = false), 0) * 100, 2) >= 70 
                    THEN 'fair'
                    ELSE 'poor'
                END AS herd_immunity_status
            FROM child_immunization ci
            JOIN immunization_type it ON ci.immunization_type_id = it.immunization_type_id
            WHERE DATE_PART('year', ci.date_given) = %s
            GROUP BY it.immunization_type_name
        )
        SELECT 
            (SELECT json_agg(vc) FROM vaccine_coverage vc) AS vaccine_coverage,
            (SELECT json_agg(st) FROM seasonal_trends st) AS seasonal_trends,
            (SELECT json_agg(yoy) FROM yoy_comparison yoy) AS yoy_comparison,
            (SELECT json_agg(hi) FROM herd_immunity_estimate hi) AS herd_immunity
        """
        
        result = self.db_connection.execute_query_to_dict(query, (year, year, year, year))
        return result[0] if result else {}

    def get_annual_growth_development(self, year: int) -> Dict[str, Any]:
        """
        Annual Growth & Development Trend Report
        - Average weight and height gain per age group
        - Identification of chronic malnutrition trends
        - Purok-level disparities
        - Correlation with feeding, supplement, and screening programs
        """
        query = """
        WITH annual_monitoring AS (
            SELECT 
                cml.child_monitoring_id,
                cml.child_record_id,
                cml.check_date,
                cml.age,
                cml.weight,
                cml.height,
                chr.family_id,
                p.birthdate,
                CASE 
                    WHEN cml.age <= 6 THEN '0-6 months'
                    WHEN cml.age <= 12 THEN '7-12 months'
                    WHEN cml.age <= 24 THEN '13-24 months'
                    WHEN cml.age <= 36 THEN '25-36 months'
                    ELSE '37+ months'
                END AS age_group
            FROM child_monitoring_log cml
            JOIN child_health_record chr ON cml.child_record_id = chr.child_record_id
            JOIN person p ON chr.person_id = p.person_id
            WHERE DATE_PART('year', cml.check_date) = %s
              AND chr.is_transferred = false
        ),
        growth_by_age_group AS (
            SELECT 
                age_group,
                COUNT(DISTINCT child_record_id) AS children_count,
                ROUND(AVG(weight), 2) AS avg_weight,
                ROUND(AVG(height), 2) AS avg_height,
                ROUND(STDDEV(weight), 2) AS weight_stddev,
                ROUND(STDDEV(height), 2) AS height_stddev,
                MIN(weight) AS min_weight,
                MAX(weight) AS max_weight,
                MIN(height) AS min_height,
                MAX(height) AS max_height
            FROM annual_monitoring
            GROUP BY age_group
            ORDER BY 
                CASE age_group
                    WHEN '0-6 months' THEN 1
                    WHEN '7-12 months' THEN 2
                    WHEN '13-24 months' THEN 3
                    WHEN '25-36 months' THEN 4
                    ELSE 5
                END
        ),
        chronic_malnutrition AS (
            SELECT 
                am.child_record_id,
                p.first_name || ' ' || p.last_name AS child_name,
                COUNT(*) AS check_count,
                ROUND(AVG(am.weight), 2) AS avg_weight,
                ROUND(AVG(am.height), 2) AS avg_height,
                COUNT(CASE WHEN am.weight < 10 AND am.age <= 12 THEN 1 
                           WHEN am.weight < 15 AND am.age BETWEEN 13 AND 24 THEN 1
                           WHEN am.weight < 20 AND am.age > 24 THEN 1 END) AS underweight_checks,
                chr.family_id AS purok
            FROM annual_monitoring am
            JOIN child_health_record chr ON am.child_record_id = chr.child_record_id
            JOIN person p ON chr.person_id = p.person_id
            GROUP BY am.child_record_id, p.first_name, p.last_name, chr.family_id
            HAVING COUNT(CASE WHEN am.weight < 10 AND am.age <= 12 THEN 1 
                              WHEN am.weight < 15 AND am.age BETWEEN 13 AND 24 THEN 1
                              WHEN am.weight < 20 AND am.age > 24 THEN 1 END) >= 2
            ORDER BY underweight_checks DESC
        ),
        purok_disparities AS (
            SELECT 
                chr.family_id AS purok,
                COUNT(DISTINCT am.child_record_id) AS children_count,
                ROUND(AVG(am.weight), 2) AS avg_weight,
                ROUND(AVG(am.height), 2) AS avg_height,
                COUNT(CASE WHEN am.weight < 10 AND am.age <= 12 THEN 1 
                           WHEN am.weight < 15 AND am.age BETWEEN 13 AND 24 THEN 1
                           WHEN am.weight < 20 AND am.age > 24 THEN 1 END) AS malnutrition_cases,
                ROUND(COUNT(CASE WHEN am.weight < 10 AND am.age <= 12 THEN 1 
                                 WHEN am.weight < 15 AND am.age BETWEEN 13 AND 24 THEN 1
                                 WHEN am.weight < 20 AND am.age > 24 THEN 1 END)::numeric / 
                      NULLIF(COUNT(DISTINCT am.child_record_id), 0) * 100, 2) AS malnutrition_rate
            FROM annual_monitoring am
            JOIN child_health_record chr ON am.child_record_id = chr.child_record_id
            WHERE chr.family_id IS NOT NULL
            GROUP BY chr.family_id
            ORDER BY malnutrition_rate DESC
        ),
        program_correlation AS (
            SELECT 
                'Feeding Type' AS program_name,
                ft.feeding_type_name AS program_value,
                COUNT(DISTINCT am.child_record_id) AS children_count,
                ROUND(AVG(am.weight), 2) AS avg_weight,
                ROUND(AVG(am.height), 2) AS avg_height
            FROM annual_monitoring am
            JOIN feeding_type_nwbrn_scrnng ftns ON am.child_record_id = ftns.child_record_id
            JOIN feeding_type ft ON ftns.feeding_type_id = ft.feeding_type_id
            GROUP BY ft.feeding_type_name
            
            UNION ALL
            
            SELECT 
                'Iron Supplementation' AS program_name,
                CASE 
                    WHEN cisr.date_completed IS NOT NULL THEN 'Completed'
                    WHEN cisr.date_started IS NOT NULL THEN 'Ongoing'
                    ELSE 'Not Started'
                END AS program_value,
                COUNT(DISTINCT am.child_record_id) AS children_count,
                ROUND(AVG(am.weight), 2) AS avg_weight,
                ROUND(AVG(am.height), 2) AS avg_height
            FROM annual_monitoring am
            LEFT JOIN child_iron_supplement_record cisr ON am.child_record_id = cisr.child_record_id
            GROUP BY program_value
            
            UNION ALL
            
            SELECT 
                'Low Birth Weight' AS program_name,
                CASE 
                    WHEN csa.is_low_birth_weight = true THEN 'LBW'
                    ELSE 'Normal Birth Weight'
                END AS program_value,
                COUNT(DISTINCT am.child_record_id) AS children_count,
                ROUND(AVG(am.weight), 2) AS avg_weight,
                ROUND(AVG(am.height), 2) AS avg_height
            FROM annual_monitoring am
            JOIN child_screening_assessment csa ON am.child_record_id = csa.child_record_id
            GROUP BY program_value
        )
        SELECT 
            (SELECT json_agg(gag) FROM growth_by_age_group gag) AS growth_by_age_group,
            (SELECT json_agg(cm) FROM chronic_malnutrition cm) AS chronic_malnutrition,
            (SELECT json_agg(pd) FROM purok_disparities pd) AS purok_disparities,
            (SELECT json_agg(pc) FROM program_correlation pc) AS program_correlation
        """
        
        result = self.db_connection.execute_query_to_dict(query, (year,))
        return result[0] if result else {}

    