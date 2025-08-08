class BatchDataUtility:
    
    @staticmethod
    def batch_data_generator(bulk_data: list, batch_size: int) -> list:
        """
        Generator to yield batches of data from the bulk data.
        
        :param bulk_data: List of data to be batched.
        :param batch_size: Size of each batch.
        :return: Yields a batch of data.
        """
        for i in range(0, len(bulk_data), batch_size):
            yield bulk_data[ i : i + batch_size ]