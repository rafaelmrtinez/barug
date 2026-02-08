# Temporary fix file - copy this section to replace lines 380-415 in kp18.py

        # -------- THIS date trio - parse from single date field --------
        ph_today = _dt.now(ZoneInfo("Asia/Manila")).date()
        
        this_date_input = out.get("this_date", "").strip()
        if this_date_input and not this_date_input.lower() in ("this date", "date entered"):
            parsed = self._try_parse_date(this_date_input)
            if parsed:
                out["this_date"] = str(parsed.day)
                out["this_month"] = parsed.strftime("%B")
                out["this_year"] = str(parsed.year)
            else:
                out["this_date"] = str(ph_today.day)
                out["this_month"] = ph_today.strftime("%B")
                out["this_year"] = str(ph_today.year)
        else:
            out["this_date"] = str(ph_today.day)
            out["this_month"] = ph_today.strftime("%B")
            out["this_year"] = str(ph_today.year)

        # -------- Date Notified trio - parse from single date field --------
        date_notified_input = out.get("date_notified", "").strip()
        if date_notified_input and not date_notified_input.lower() in ("date notified", "date notifi"):
            parsed = self._try_parse_date(date_notified_input)
            if parsed:
                out["date_notified"] = str(parsed.day)
                out["month_notified"] = parsed.strftime("%B")
                out["year_notified"] = str(parsed.year)
            else:
                out["date_notified"] = str(ph_today.day)
                out["month_notified"] = ph_today.strftime("%B")
                out["year_notified"] = str(ph_today.year)
        else:
            out["date_notified"] = str(ph_today.day)
            out["month_notified"] = ph_today.strftime("%B")
            out["year_notified"] = str(ph_today.year)
