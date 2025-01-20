# Part 2: Multiplication and Division of Two Numbers
# Ask user for input
num1 = float(input("Enter the first number: "))
num2 = float(input("Enter the second number: "))

# Perform multiplication
multiplication_result = num1 * num2
print(f"The result of multiplication is: {multiplication_result}")

# Perform division
if num2 != 0:
    division_result = num1 / num2
    print(f"The result of division is: {division_result}")
else:
    print("Division by zero is not allowed.")