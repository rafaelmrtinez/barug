class PostgreSQLTypeConversionUtility:
    
    @staticmethod
    def to_pg_array(int_list: list[int] | None) -> str | None:
        if not int_list:
            return None
        # PostgreSQL array literal syntax: {1,2,3}
        return "{" + ",".join(str(i) for i in int_list) + "}"