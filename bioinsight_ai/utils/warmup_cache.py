import os
import pandas as pd
import bdikit as bdi

# Your data
data = {
   'Name': ['Alice', 'Bob', 'Charlie', 'Diana'],
   'Age': [25, 30, 22, 28],
   'City': ['New York', 'London', 'Paris', 'Tokyo']
}
source_dataset = pd.DataFrame(data)
target_dataset = 'gdc'
method = 'magneto_ft_bp'

# Call BDI
matches = bdi.match_schema(source_dataset, target=target_dataset, method=method)
print(matches)
