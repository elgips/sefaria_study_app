import os
os.environ["QT_QPA_PLATFORM"] = "xcb"  # Force X11 backend to avoid Wayland issues on Linux

from PyQt6.QtWidgets import QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem, QPushButton, QVBoxLayout, QWidget, QDialog, QTextBrowser, QMessageBox, QProgressDialog, QFileDialog
from PyQt6.QtCore import Qt
import requests
import json
import sys
import logging
import time

# Set up logging for debugging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BookSelectionTab(QWidget):
    """
    Standalone Book Selection tab for selecting books/categories from Sefaria's toc.
    Fetches toc from Sefaria API, displays in Hebrew, saves only selected items (no sub-items) with Hebrew, English names, and parent categories.
    Output JSON contains reading_list and he_to_en for selected items only, with no duplicates.
    """
    def __init__(self):
        super().__init__()
        logger.debug("Initializing BookSelectionTab")
        self.toc = []
        self.he_to_en = {}
        self.reading_list = []
        self.selected_he_to_en = {}
        self.fetch_toc()
        self.setup_ui()

    def fetch_toc(self):
        """Fetch toc from Sefaria API or load from local file if recent, and initialize he_to_en."""
        logger.debug("Starting fetch_toc")
        progress_dialog = QProgressDialog("שואב נתונים מ-Sefaria...", "ביטול", 0, 100, self)
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setValue(0)
        toc_file = "sefaria_toc.json"
        fetch_from_api = True
    
        # Check if local TOC file exists and is less than 14 days old
        try:
            if os.path.exists(toc_file):
                file_mtime = os.path.getmtime(toc_file)
                current_time = time.time()
                two_weeks_ago = current_time - (14 * 24 * 60 * 60)  # 14 days in seconds
                if file_mtime > two_weeks_ago:
                    logger.debug(f"Loading TOC from local file: {toc_file}")
                    with open(toc_file, "r", encoding="utf-8") as f:
                        self.toc = json.load(f)
                    logger.debug(f"Loaded TOC from file: {len(self.toc)} items")
                    fetch_from_api = False
        except Exception as e:
            logger.error(f"Error checking/loading local TOC file: {str(e)}")
            fetch_from_api = True
    
        # Fetch from API if needed
        if fetch_from_api:
            try:
                logger.debug("Sending request to Sefaria API: https://www.sefaria.org/api/index/")
                response = requests.get("https://www.sefaria.org/api/index/")
                response.raise_for_status()
                self.toc = response.json()
                logger.debug(f"Received toc data from API: {len(self.toc)} items")
                # Save TOC to local file
                try:
                    with open(toc_file, "w", encoding="utf-8") as f:
                        json.dump(self.toc, f, ensure_ascii=False, indent=2)
                    logger.debug(f"Saved TOC to {toc_file}")
                except Exception as e:
                    logger.error(f"Error saving TOC to file: {str(e)}")
            except Exception as e:
                logger.error(f"Error fetching toc from API: {str(e)}")
                progress_dialog.close()
                QMessageBox.warning(self, "שגיאה", f"שגיאה בשאיבת נתונים: {str(e)}")
                self.toc = []
                self.he_to_en = {}
                progress_dialog.setValue(100)
                return
    
        progress_dialog.setValue(50)
        # Build he_to_en mappings for all items
        def extract_mappings(items):
            for item in items:
                he_title = item.get("heTitle", item.get("heCategory", ""))
                en_title = item.get("title", item.get("category", ""))
                if he_title and en_title:
                    self.he_to_en[he_title] = en_title
                    logger.debug(f"Added mapping: {he_title} -> {en_title}")
                extract_mappings(item.get("contents", []))
        extract_mappings(self.toc)
        logger.debug(f"Total he_to_en mappings: {len(self.he_to_en)}")
        
        # Load existing selections if available
        try:
            with open("book_selection.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                self.reading_list = data.get("reading_list", [])
                self.selected_he_to_en = data.get("he_to_en", {})
                logger.debug(f"Loaded existing JSON: reading_list={self.reading_list}, he_to_en={self.selected_he_to_en}")
                # Update toc with saved selections
                def mark_selections(items):
                    for item in items:
                        he_title = item.get("heTitle", item.get("heCategory", ""))
                        if he_title in self.selected_he_to_en:
                            item["selected"] = True
                            logger.debug(f"Marked item as selected: {he_title}")
                        else:
                            item["selected"] = False
                        mark_selections(item.get("contents", []))
                mark_selections(self.toc)
        except FileNotFoundError:
            logger.debug("No existing book_selection.json found")
        
        progress_dialog.setValue(100)
        progress_dialog.close()
        logger.debug("Completed fetch_toc")
    
    def setup_ui(self):
        logger.debug("Setting up UI")
        layout = QVBoxLayout()
        
        # Tree widget for hierarchical display of books/categories
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("בחירת ספרים וקטגוריות")
        self.tree.itemChanged.connect(self.update_selection)
        self.populate_tree()
        layout.addWidget(self.tree)
        
        # Save button
        self.save_button = QPushButton("עדכן רשימה")
        self.save_button.clicked.connect(self.save_selection)
        layout.addWidget(self.save_button)
        
        # Save as button
        self.save_as_button = QPushButton("שמור רשימה בשם")
        self.save_as_button.clicked.connect(self.save_selection_as)
        layout.addWidget(self.save_as_button)
        
        # Load button
        self.load_button = QPushButton("טען רשימה")
        self.load_button.clicked.connect(self.load_selection)
        layout.addWidget(self.load_button)
        
        # JSON view button
        self.json_button = QPushButton("הצג JSON של רשימת הספרים")
        self.json_button.clicked.connect(self.show_json)
        layout.addWidget(self.json_button)
        
        # Clear list button
        self.clear_button = QPushButton("נקה רשימה")
        self.clear_button.clicked.connect(self.clear_selection)
        layout.addWidget(self.clear_button)
        
        # Exit button
        self.exit_button = QPushButton("יציאה")
        self.exit_button.clicked.connect(QApplication.quit)
        layout.addWidget(self.exit_button)

        
        self.setLayout(layout)
        logger.debug("UI setup completed")

    def populate_tree(self):
        """Populate tree with toc items, showing only Hebrew titles/categories."""
        logger.debug("Populating tree")
        self.tree.clear()
        for item in self.toc:
            self.add_tree_item(item, self.tree.invisibleRootItem())
        logger.debug("Tree population completed")

    def add_tree_item(self, item, parent):
        """Recursively add items to tree with Hebrew titles/categories."""
        display_text = item.get("heTitle", item.get("heCategory", ""))
        if not display_text:
            logger.debug("Skipping item with no display text")
            return
        tree_item = QTreeWidgetItem(parent)
        tree_item.setText(0, display_text)
        tree_item.setFlags(tree_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        tree_item.setCheckState(0, Qt.CheckState.Checked if item.get("selected", False) else Qt.CheckState.Unchecked)
        tree_item.setData(0, Qt.ItemDataRole.UserRole, item)
        logger.debug(f"Added tree item: {display_text}, selected={item.get('selected', False)}")
        
        # Recursively add sub-items
        for sub_item in item.get("contents", []):
            self.add_tree_item(sub_item, tree_item)

    def update_selection(self, item, column):
        """Update selected state of item in self.toc without affecting sub-items."""
        item_data = item.data(0, Qt.ItemDataRole.UserRole)
        if item_data:
            he_title = item_data.get("heTitle", item_data.get("heCategory", ""))
            selected = item.checkState(0) == Qt.CheckState.Checked
            logger.debug(f"Updating selection for item: {he_title}, selected={selected}")
            # Update the corresponding item in self.toc
            def update_toc_selection(items, target_he_title, target_selected):
                for toc_item in items:
                    toc_he_title = toc_item.get("heTitle", toc_item.get("heCategory", ""))
                    if toc_he_title == target_he_title:
                        toc_item["selected"] = target_selected
                        logger.debug(f"Updated toc item: {toc_he_title}, selected={target_selected}")
                        return True
                    if update_toc_selection(toc_item.get("contents", []), target_he_title, target_selected):
                        return True
                return False
            update_toc_selection(self.toc, he_title, selected)

    def get_category_path(self, item, toc, path=None):
        """Recursively find the category path for an item in the TOC."""
        if path is None:
            path = []
        for toc_item in toc:
            he_title = toc_item.get("heTitle", toc_item.get("heCategory", ""))
            if he_title == item.get("heTitle", item.get("heCategory", "")):
                # Found the item, return the current path
                return path + [he_title]
            # Recursively search in sub-items
            sub_path = self.get_category_path(item, toc_item.get("contents", []), path + [he_title])
            if sub_path:
                return sub_path
        return None

    def save_selection(self):
        """Save only selected books/categories to reading_list and book_selection.json, including parent categories."""
        logger.debug("Starting save_selection")
        self.reading_list = []
        self.selected_he_to_en = {}  # Only include mappings for selected items
        unique_items = set()  # To avoid duplicates
        def collect_selections(items):
            for item in items:
                if item.get("selected", False):
                    he_title = item.get("heTitle", item.get("heCategory", ""))
                    en_title = item.get("title", item.get("category", ""))
                    if he_title and en_title:
                        # Get the category path for this item
                        categories = self.get_category_path(item, self.toc)
                        if categories:
                            # Remove the item itself from categories (only include parent categories)
                            if categories[-1] == he_title:
                                categories = categories[:-1]
                            item_dict = {
                                "he_title": he_title,
                                "en_title": en_title,
                                "categories": categories
                            }
                            if (he_title, en_title) not in unique_items:
                                unique_items.add((he_title, en_title))
                                self.reading_list.append(item_dict)
                                self.selected_he_to_en[he_title] = en_title
                                logger.debug(f"Added to reading_list: {item_dict}")
                            else:
                                logger.debug(f"Skipped duplicate: ({he_title}, {en_title})")
                collect_selections(item.get("contents", []))
        
        collect_selections(self.toc)
        logger.debug(f"Collected reading_list: {self.reading_list}")
        logger.debug(f"Collected selected_he_to_en: {self.selected_he_to_en}")
        try:
            with open("book_selection.json", "w", encoding="utf-8") as f:
                json.dump({"reading_list": self.reading_list, "he_to_en": self.selected_he_to_en}, f, ensure_ascii=False, indent=2)
                logger.debug("Successfully wrote to book_selection.json")
            QMessageBox.information(self, "הצלחה", "רשימת הספרים והקטגוריות עודכנה בהצלחה!")
        except Exception as e:
            logger.error(f"Error saving JSON: {str(e)}")
            QMessageBox.warning(self, "שגיאה", f"שגיאה בשמירת הקובץ: {str(e)}")
        logger.debug("Completed save_selection")

    def save_selection_as(self):
        """Save selected books/categories to a user-specified JSON file, including parent categories."""
        logger.debug("Starting save_selection_as")
        file_name, _ = QFileDialog.getSaveFileName(self, "שמור רשימה בשם", "", "JSON Files (*.json)")
        if not file_name:
            logger.debug("Save as cancelled by user")
            return
        self.reading_list = []
        self.selected_he_to_en = {}  # Only include mappings for selected items
        unique_items = set()  # To avoid duplicates
        def collect_selections(items):
            for item in items:
                if item.get("selected", False):
                    he_title = item.get("heTitle", item.get("heCategory", ""))
                    en_title = item.get("title", item.get("category", ""))
                    if he_title and en_title:
                        # Get the category path for this item
                        categories = self.get_category_path(item, self.toc)
                        if categories:
                            # Remove the item itself from categories (only include parent categories)
                            if categories[-1] == he_title:
                                categories = categories[:-1]
                            item_dict = {
                                "he_title": he_title,
                                "en_title": en_title,
                                "categories": categories
                            }
                            if (he_title, en_title) not in unique_items:
                                unique_items.add((he_title, en_title))
                                self.reading_list.append(item_dict)
                                self.selected_he_to_en[he_title] = en_title
                                logger.debug(f"Added to reading_list: {item_dict}")
                            else:
                                logger.debug(f"Skipped duplicate: ({he_title}, {en_title})")
                collect_selections(item.get("contents", []))
        
        collect_selections(self.toc)
        logger.debug(f"Collected reading_list: {self.reading_list}")
        logger.debug(f"Collected selected_he_to_en: {self.selected_he_to_en}")
        try:
            with open(file_name, "w", encoding="utf-8") as f:
                json.dump({"reading_list": self.reading_list, "he_to_en": self.selected_he_to_en}, f, ensure_ascii=False, indent=2)
                logger.debug(f"Successfully wrote to {file_name}")
            QMessageBox.information(self, "הצלחה", f"רשימת הספרים והקטגוריות נשמרה ב-{file_name}!")
        except Exception as e:
            logger.error(f"Error saving JSON: {str(e)}")
            QMessageBox.warning(self, "שגיאה", f"שגיאה בשמירת הקובץ: {str(e)}")
        logger.debug("Completed save_selection_as")

    def load_selection(self):
        """Load selections from a user-specified JSON file."""
        logger.debug("Starting load_selection")
        file_name, _ = QFileDialog.getOpenFileName(self, "טען רשימה", "", "JSON Files (*.json)")
        if not file_name:
            logger.debug("Load cancelled by user")
            return
        try:
            with open(file_name, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.reading_list = data.get("reading_list", [])
                self.selected_he_to_en = data.get("he_to_en", {})
                logger.debug(f"Loaded JSON: reading_list={self.reading_list}, he_to_en={self.selected_he_to_en}")
                # Update toc with loaded selections
                def mark_selections(items):
                    for item in items:
                        he_title = item.get("heTitle", item.get("heCategory", ""))
                        item["selected"] = he_title in self.selected_he_to_en
                        logger.debug(f"Updated item: {he_title}, selected={item['selected']}")
                        mark_selections(item.get("contents", []))
                mark_selections(self.toc)
                # Refresh tree to reflect loaded selections
                self.populate_tree()
                QMessageBox.information(self, "הצלחה", f"רשימת הספרים והקטגוריות נטענה מ-{file_name}!")
        except Exception as e:
            logger.error(f"Error loading JSON: {str(e)}")
            QMessageBox.warning(self, "שגיאה", f"שגיאה בטעינת הקובץ: {str(e)}")
        logger.debug("Completed load_selection")

    def show_json(self):
        """Show JSON data in a read-only dialog with a close button."""
        logger.debug("Opening JSON dialog")
        dialog = QDialog(self)
        dialog.setWindowTitle("תצוגת JSON")
        layout = QVBoxLayout()
        json_text = QTextBrowser()
        json_data = {
            "reading_list": self.reading_list,
            "he_to_en": self.selected_he_to_en
        }
        json_text.setText(json.dumps(json_data, ensure_ascii=False, indent=2))
        json_text.setReadOnly(True)
        layout.addWidget(json_text)
        
        # Close button for JSON dialog
        close_button = QPushButton("סגור")
        close_button.clicked.connect(dialog.close)
        layout.addWidget(close_button)
        
        dialog.setLayout(layout)
        dialog.resize(600, 400)
        dialog.exec()
        logger.debug("Closed JSON dialog")
    
    def clear_selection(self):
        """Clear all selections in the TOC and reset reading_list and selected_he_to_en."""
        logger.debug("Starting clear_selection")
        self.reading_list = []
        self.selected_he_to_en = {}
        
        # Reset selected state in TOC
        def reset_selections(items):
            for item in items:
                item["selected"] = False
                reset_selections(item.get("contents", []))
        reset_selections(self.toc)
        
        # Refresh tree to reflect cleared selections
        self.populate_tree()
        
        # Save empty selection to JSON
        try:
            with open("book_selection.json", "w", encoding="utf-8") as f:
                json.dump({"reading_list": self.reading_list, "he_to_en": self.selected_he_to_en}, f, ensure_ascii=False, indent=2)
                logger.debug("Successfully cleared and saved to book_selection.json")
            QMessageBox.information(self, "הצלחה", "רשימת הספרים והקטגוריות נוקתה בהצלחה!")
        except Exception as e:
            logger.error(f"Error saving cleared JSON: {str(e)}")
            QMessageBox.warning(self, "שגיאה", f"שגיאה בניקוי הרשימה: {str(e)}")
        logger.debug("Completed clear_selection")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("בחירת ספרים - Sefaria")
        self.book_selection_tab = BookSelectionTab()
        self.setCentralWidget(self.book_selection_tab)
        self.resize(600, 400)

if __name__ == "__main__":
    logger.debug("Starting application")
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    logger.debug("Main window shown")
    sys.exit(app.exec())