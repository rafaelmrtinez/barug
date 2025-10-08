class JSONCustomUtility:
    
    @staticmethod
    def clean_empty_strings(data: dict):
        for k, v in data.items():
            if isinstance(v, str) and v.strip() == "":
                data[k] = None
            elif isinstance(v, list):
                data[k] = [JSONCustomUtility.clean_empty_strings(i) if isinstance(i, dict) else i for i in v]
            elif isinstance(v, dict):
                data[k] = JSONCustomUtility.clean_empty_strings(v)
        return data