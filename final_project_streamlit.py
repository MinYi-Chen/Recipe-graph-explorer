"""Streamlit web application for exploring recipe connections through a graph-based interface.

This app provides five interactive modes:
1. Search recipes by multiple ingredients
2. Compare shared ingredients between two meals
3. Rank ingredients by frequency of use
4. Find shortest path between any two ingredients using BFS
5. Recommend recipes based on available pantry ingredients and optional exclusions
"""

import altair as alt
import pandas as pd
import streamlit as st

from final_project import MealDBAPIClient, Recipe, RecipeGraph, RecipeRecommender

st.set_page_config(page_title="Recipe Graph Explorer")


@st.cache_resource
def load_data():
    """Fetch all recipes from TheMealDB API and build the recipe graph.

    This function is cached using @st.cache_resource so the API is only called
    once when the app first loads, improving performance on subsequent runs.

    Returns:
        RecipeGraph: A fully populated graph with all meals and ingredient connections.
    """
    # Create the API client that will retrieve recipe data from TheMealDB.
    client = MealDBAPIClient()
    meals_data = client.fetch_all_recipes()

    # Build the graph by adding each API response as a Recipe node with ingredient links.
    graph = RecipeGraph()
    if meals_data:
        for data in meals_data:
            graph.add_recipe_to_graph(Recipe(data))
    return graph


def show_recipe_details(graph, recipe_name):
    """Display a compact detail view for a selected recipe.

    This helper keeps the layout logic separate from the main mode handlers so
    the page stays easier to read and reuse.
    """
    # Look up the full Recipe object from the graph's catalog.
    recipe = graph.get_recipe_details(recipe_name)
    if recipe is None:
        st.warning("Recipe details could not be found.")
        return

    # Use an expander so users can open recipe details only when needed.
    with st.expander(f"{recipe.name}"):
        st.markdown(f"**Category:** {recipe.category}")
        st.markdown(f"**Ingredients:** {', '.join(recipe.ingredients)}")

        # Strip leading/trailing whitespace from instructions to improve formatting in the app.
        st.markdown("**Instructions:**")
        with st.container(height=250, border=True):
            st.text(recipe.instructions.strip())


# Load the graph data once at app startup so the app can reuse it across interactions.
my_graph = load_data()
# Create a RecipeRecommender instance using the graph's recipe catalog for the pantry recommendation mode.
my_recommender = RecipeRecommender(my_graph.recipe_catalog)

# Extract all recipe names for the meal comparison controls.
all_recipes = sorted(my_graph.recipe_catalog.keys())

# Extract ingredient nodes by filtering out recipe nodes from the graph.
# Ingredient nodes are the ones that do not appear in the recipe catalog.
all_ingredients = sorted(
    [node for node in my_graph.graph.keys() if node not in my_graph.recipe_catalog]
)

# Display the main title and a short description of the app's purpose.
st.title("Final Project: Recipe Graph")
st.caption(
    "Explore how meals and ingredients connect through search, comparison, ranking, shortest paths, and pantry-based recommendations."
)

# Stop early if the API did not return any data, because the UI would not have anything useful to show.
if not my_graph.graph:
    st.error("No recipe data was loaded. Please try refreshing the app.")
    st.stop()

# Create the main mode selector so users can switch between the five features.
mode = st.selectbox(
    "Select a Mode:",
    [
        "1. Ingredient Search",
        "2. Compare Two Meals",
        "3. Top Ingredients Ranking",
        "4. Shortest Path (BFS)",
        "5. Pantry Recommendation"
    ],
)

# Add a visual separator line to separate the navigation from the active tool area.
st.write("---")

# Render the interface for the selected mode.
if mode == "1. Ingredient Search":
    # Ingredient search mode lets users find every recipe that contains all chosen ingredients.
    st.subheader("Ingredient Search")
    st.write("Find recipes that use **all** selected ingredients.")
    selected_ings = st.multiselect("Select ingredients:", all_ingredients)

    if st.button("Search"):
        # Prevent empty searches so the result message is more meaningful.
        if not selected_ings:
            st.warning("Please select at least one ingredient before searching.")
        else:
            results = my_graph.search_multiple_ingredients(selected_ings)
            if results:
                # Show a success message first.
                st.success(f"Found {len(results)} matching recipe(s).")
                
                # Loop through all matching recipes and display them as expanders.
                for recipe_name in results:
                    show_recipe_details(my_graph, recipe_name)
            else:
                st.warning("No recipes matched all of the selected ingredients.")

elif mode == "2. Compare Two Meals":
    # Comparison mode shows ingredients shared by two selected recipes.
    st.subheader("Compare Two Meals")
    st.write("See which ingredients two meals have in common.")

    meal_1 = st.selectbox("First meal:", all_recipes)
    meal_2 = st.selectbox("Second meal:", all_recipes)

    if st.button("Compare"):
        # Give a helpful note if the user selected the same meal twice.
        if meal_1 == meal_2:
            st.info("You selected the same meal twice, so every ingredient is shared.")

        # Compute the shared ingredient list from the graph neighbors.
        shared = my_graph.compare_two_meals(meal_1, meal_2)
        if shared:
            shared_str = ", ".join(shared)
            st.success(f"These meals share {len(shared)} ingredient(s):\n\n**{shared_str}**")
        else:
            st.warning("These meals do not share any ingredients.")

        # Display both selected recipes side by side for easier comparison.
        col1, col2 = st.columns(2)
        with col1:
            show_recipe_details(my_graph, meal_1)
        with col2:
            show_recipe_details(my_graph, meal_2)

elif mode == "3. Top Ingredients Ranking":
    # Ranking mode shows the most frequently used ingredients across all recipes.
    st.subheader("Top Ingredients Ranking")
    st.write("See the most frequently used ingredients in the recipe network.")
    top_n = st.number_input("How many items to show?", min_value=1, max_value=20, value=10)

    if st.button("Show Ranking"):
        # Request the top-N ingredients from the graph based on connection count.
        top = my_graph.get_top_ingredients(int(top_n))
        if top:
            st.success(f"Showing the top {len(top)} ingredient(s) in the network.")
            # Print a simple ranked list above the chart for a quick text summary.
            for i, (name, count) in enumerate(top, 1):
                st.write(f"{i}. {name} ({count} recipes)")

            # Build a DataFrame so the chart can render the ingredient counts cleanly.
            df = pd.DataFrame(top, columns=["Ingredient", "Count"])
            df = df.sort_values("Count", ascending=False)
            # Use an explicit Altair chart so the descending order is preserved.
            chart = (
                alt.Chart(df)
                .mark_bar()
                .encode(
                    x=alt.X(
                        "Ingredient:N",
                        sort=alt.EncodingSortField(field="Count", order="descending"),
                    ),
                    y=alt.Y("Count:Q"),
                    tooltip=["Ingredient:N", "Count:Q"],
                )
            )
            st.altair_chart(chart, use_container_width=True)
        else:
            st.warning("No ingredient ranking is available.")

elif mode == "4. Shortest Path (BFS)":
    # Pathfinding mode uses breadth-first search to connect one ingredient to another.
    st.subheader("Shortest Path (BFS)")
    st.write("Find the shortest connection between two ingredients.")
    st.write("This tool finds the most direct bridge between two ingredients through shared recipes. It reveals how different culinary components are linked across the global network of food.")
    start_ing = st.selectbox("Start ingredient:", all_ingredients)
    end_ing = st.selectbox("End ingredient:", all_ingredients)
    # a dynamic multiselect for the top 10 ingredients.
    # First, dynamically fetch the current top 10 ingredients from the graph.
    top_10_items = my_graph.get_top_ingredients(10)
    top_10_names = [item[0] for item in top_10_items]
    
    # Allow users to select specific staples they want to exclude from the path.
    excluded_staples = st.multiselect(
        "Select common staples to exclude from the path:",
        options=top_10_names,
        default=[] # By default, nothing is excluded
    )

    if st.button("Find Path"):
        # Convert selected staples to a set, but never exclude the chosen start or end ingredient.
        # find_shortest_path() also enforces this internally.
        safe_excluded = set(excluded_staples) - {start_ing, end_ing}
        result = my_graph.find_shortest_path(start_ing, end_ing, exclude_nodes=safe_excluded)

        if result[0] != -1:
            distance = result[0]
            actual_path = result[1]
            # Show both the hop count and the full alternating ingredient/meal path.
            st.success(f"A path was found with {distance} ingredient-to-ingredient hop(s).")
            path_with_labels = []
            for i, item in enumerate(actual_path):
                if i % 2 == 0:
                    # Ingredient nodes are at even indices, so we label them clearly.
                    path_with_labels.append(f"**[Ingredient: {item.title()}]**")
                else:
                    # Recipe nodes are at odd indices, so we label them differently to distinguish from ingredients.
                    path_with_labels.append(f"*(Recipe: {item})*")
                    
            st.markdown(" -> ".join(path_with_labels))
        else:
            # The graph returned no valid route between the chosen ingredients.
            st.warning("No path found between those two ingredients.")

elif mode == "5. Pantry Recommendation":
    st.subheader("Pantry Recommendation")
    st.write("Find recipes based on ingredients you already have, and optionally avoid ingredients you do not want.")

    available_ings = st.multiselect(
        "Ingredients you have:",
        all_ingredients
    )

    excluded_ings = st.multiselect(
        "Ingredients to avoid:",
        all_ingredients
    )

    top_n = st.number_input(
        "How many recommendations to show?",
        min_value=1,
        max_value=20,
        value=5
    )

    if st.button("Recommend Recipes"):
        if not available_ings:
            st.warning("Please select at least one ingredient you have.")
        else:
            results = my_recommender.recommend_recipes_by_pantry(
                available_ings,
                excluded_ingredients=excluded_ings,
                top_n=int(top_n)
            )

            if results:
                st.success(f"Found {len(results)} recommendation(s).")

                for item in results:
                    st.markdown(f"### {item['name']}")
                    st.write(f"Matched ingredients: {', '.join(item['matched_ingredients'])}")
                    st.write(f"Missing ingredients: {', '.join(item['missing_ingredients']) if item['missing_ingredients'] else 'None'}")
                    st.write(f"Match score: {item['matched_count']} matched, {item['missing_count']} missing")

                    show_recipe_details(my_graph, item['name'])
            else:
                st.warning("No recipes matched your pantry and exclusion filters.")