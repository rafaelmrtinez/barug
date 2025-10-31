from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional


@dataclass
class Business:
    business_id: Optional[int] = None
    business_name: Optional[str] = None
    location_description: Optional[str] = None
    business_nature: Optional[str] = None
    prev_yr_total_gross_sales: Optional[float] = None
    date_est: Optional[date] = None
    dti_sec_reg_num: Optional[str] = None
    capital_invested: Optional[float] = None
    mnthly_gross_incom_est: Optional[float] = None
    num_of_emp: Optional[int] = None
    address_id: Optional[int] = None
    business_type_id: Optional[int] = None
    business_status_id: Optional[int] = None
    ownership_type_id: Optional[int] = None
    operating_days_id: Optional[int] = None
    operating_hours_id: Optional[int] = None
    business_owner_id: Optional[int] = None
    added_by_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
