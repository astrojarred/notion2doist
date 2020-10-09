import datetime

from todoist.api import TodoistAPI
import todoist.models
import notion
from notion.client import NotionClient
from notion.collection import NotionDate
import json
from bidict import bidict
from datetime import datetime, timezone


class task:

    def __init__(self,
                 source=None,
                 task_id=None,
                 notion_task_id=None,
                 content=None,
                 done=None,
                 due=None,
                 label_ids=None,
                 label_names=None,
                 project_id=None,
                 notion_project_id=None,
                 project_name=None,
                 todoist_note_id=None,
                 ):

        self.source = source
        self.task_id = task_id
        self.content = content
        self.done = done
        self.due = due
        self.label_ids = label_ids
        self.label_names = label_names
        self.project_id = project_id
        self.project_name = project_name
        self.notion_task_id = notion_task_id
        self.notion_project_id = notion_project_id
        self.todoist_note_id = todoist_note_id

    def __repr__(self):
        return f"Task: {self.content}\n {json.dumps(self.__dict__, indent=4)}"

    def __eq__(self, other):
        return self.generate_eq_dict() == other.generate_eq_dict()

    def __getattr__(self, attr):
        return self.__dict__[attr]

    def __setattr__(self, name, value):
        super.__setattr__(self, name, value)

    def generate_eq_dict(self):

        _eq = (self.task_id, self.notion_task_id)

        return _eq

    def update(self, **kwargs):

        # check that all kwargs are valid:
        for kwarg in kwargs:
            if kwarg not in self.__dict__.keys():
                raise ValueError(f"{kwarg} is not a valid task parameter.")

        for name, value in kwargs.items():
            super.__setattr__(self, name, value)


class syncManager:

    def __init__(self, todoist_token, notion_token, notion_settings_url):
        self.api = TodoistAPI(todoist_token)
        self.client = NotionClient(token_v2=notion_token)
        self.settings = self.client.get_collection_view(notion_settings_url)

        # extract and parse settings
        self.config = {}
        self.use_groups = False
        self.sync_completed_tasks = False
        self.sync_config()

        self.tasks = self.client.get_collection_view(
            "https://www.notion.so/" + self.config["Link to task database"]
        )
        self.projects = self.client.get_collection_view(
            "https://www.notion.so/" + self.config["Link to project database"]
        )
        self.labels = self.client.get_collection_view(
            "https://www.notion.so/" + self.config["Link to label database"]
        )

        # initialize todoist api jsons
        self.old_sync = None
        self.new_sync = None
        self.old_commit = None
        self.new_commit = None

    def sync_todoist_api(self):
        self.old_sync = self.new_sync
        self.new_sync = self.api.sync()

    def commit_todoist_api(self):
        self.old_commit = self.new_commit
        self.new_commit = self.api.commit()

    def _parse_label_columns(self):
        column_list = self.config['Label column name']
        column_dict = {}
        for item in column_list.replace(" ", "").split(","):
            key, value = item.split("=")
            column_dict[key] = value
        self.config["Input label string"] = self.config['Label column name']
        self.config['Label column name'] = column_dict

    def sync_config(self):
        self.config = {row.title: row.value for row in self.settings.collection.get_rows()}  # extract settings
        self._parse_label_columns()
        self.use_groups = True if self.config["Use groups"].lower() in ["true", "yes", "y", "t"] else False
        self.sync_completed_tasks = True if self.config["Sync completed tasks"].lower() in\
                                            ["true", "yes", "y", "t"] else False


class labelManager:

    @staticmethod
    def translate_label(manager, label, source="todoist"):

        output = "notion" if source == "todoist" else "todoist"

        for row in manager.labels.collection.get_rows():
            if row.get_property(f"{source} label") == label:
                return row.get_property(f"{output} label"), row.get_property(f"{output}ID")

        return None

    @staticmethod
    def get_notion_labels(manager, row):
        """Always returns todoist label names and IDs"""

        label_config = manager.config['Label column name']
        label_names, label_ids = [], []

        for label_column in label_config.keys():
            row_labels = row.get_property(label_column)
            if not isinstance(row_labels, list):  # if column is single-select, convert it to a list
                row_labels = [row_labels]
            # add labels to list and translate to todoist labels
            for label in row_labels:
                todoist_label, todoist_id = labelManager.translate_label(manager, label, source="notion")
                label_names.append(todoist_label)
                label_ids.append(todoist_id)

        return label_names, label_ids

    @staticmethod
    def get_labels_bidict(manager):

        label_bidict = bidict({})
        for label in manager.api.labels.all():
            label_bidict[label["id"]] = label["name"]

        return label_bidict

    @staticmethod
    def get_done_labels(manager):

        done_labels = []
        for row in manager.labels.collection.get_rows():
            if row.means_done:
                done_labels.append(row.title)

        return done_labels

    @staticmethod
    def get_label_tag_columns(manager):
        """Returns a list of the columns """

        label_columns = [column for column in manager.config["Label column name"].keys()]
        column_types = [column_type for column_type in manager.config["Label column name"].values()]
        return label_columns, column_types

    @staticmethod
    def sync_labels_to_todoist(manager: syncManager):

        print("Syncing labels...")
        new_label_count = 0
        updated_label_count = 0

        # sync todoist api
        manager.sync_todoist_api()

        # get a list of labels
        labels = labelManager.get_labels_bidict(manager)

        # go label by label
        for row in manager.labels.collection.get_rows():
            # first check if the NotionID has been assigned yet
            if not row.notionID:
                row.notionID = row.id
            # then check if it has a TodoistID
            if not row.todoistID:
                # check if the name of the label matches one on todoist
                if row.todoist_label in labels.values():
                    # add todoist label id to notion
                    row.todoistID = labels.inverse[row.todoist_label]
                else:  # otherwise, add it to todoist
                    print(f"Adding new label {row.todoist_label}")
                    manager.api.labels.add(name=row.todoist_label)
                    manager.commit_todoist_api()

                    # update label_bidict and add todoistID to notion
                    labels = labelManager.get_labels_bidict(manager)
                    row.todoistID = labels.inverse[row.todoist_label]

                    new_label_count += 1  # update label count
            else:
                # check if the name is different, if so, update name in todoist
                if row.todoist_label != labels[row.todoistID]:
                    print(f"Updating label {labels[row.todoistID]} ⮕ {row.todoist_label}")
                    manager.api.labels.get_by_id(row.todoistID).update(name=row.todoist_label)
                    manager.commit_todoist_api()

                    updated_label_count += 1  # update updated label count

            # add notion IDs to table
            # for notion_label in manager.tasks.collection.get_schema_property():

        print(f"Done syncing labels. {new_label_count} label(s) added and {updated_label_count} label(s) updated")


class projectManager:

    @staticmethod
    def get_todoist_bidict(manager):

        project_bidict = bidict({})
        for project in manager.api.projects.all():
            project_bidict[project["id"]] = project["name"]

        return project_bidict

    @staticmethod
    def get_notion_bidict(manager):

        project_bidict = bidict({})
        for project in manager.projects.collection.get_rows():
            project_bidict[project.id] = project.title

        return project_bidict

    @staticmethod
    def get_cross_bidict(manager):

        cross_bidict = bidict({})
        for project in manager.projects.collection.get_rows():
            cross_bidict[project.todoistID] = project.id

        return cross_bidict

    @staticmethod
    def get_all_bidicts(manager):

        return projectManager.get_todoist_bidict(manager), \
               projectManager.get_notion_bidict(manager), \
               projectManager.get_cross_bidict(manager)

    @staticmethod
    def sync_projects(manager: syncManager):

        print("Syncing projects...")
        new_project_count = 0
        updated_project_count = 0

        # sync todoist api
        manager.sync_todoist_api()

        # get a list of labels
        todoist_projects, notion_projects, cross_projects = projectManager.get_all_bidicts(manager)

        # go label by label
        for project in manager.projects.collection.get_rows():
            # first check if it has a TodoistID
            if not project.todoistID:
                # check if the name of the project matches one on todoist
                if project.title in todoist_projects.values():
                    # add todoist project id to notion
                    project.todoistID = todoist_projects.inverse[project.title]
                else:  # otherwise, add it to todoist
                    print(f"Adding new project {project.title}")
                    manager.api.projects.add(name=project.title)
                    manager.commit_todoist_api()

                    # update label_bidict and add todoistID to notion
                    todoist_projects = projectManager.get_todoist_bidict(manager)
                    project.todoistID = todoist_projects.inverse[project.title]

                    new_project_count += 1  # update label count
            else:
                # check if the project name is different, if so, update name in todoist
                if project.title != todoist_projects[project.todoistID]:
                    print(f"Updating project name {todoist_projects[project.todoistID]} ⮕ {project.title}")
                    manager.api.projects.get_by_id(project.todoistID).update(name=project.title)
                    manager.commit_todoist_api()

                    updated_project_count += 1  # update updated label count

            # add notion IDs to table
            # for notion_label in manager.tasks.collection.get_schema_property():

        print(f"Done syncing projects. {new_project_count} project(s) added "
              f"and {updated_project_count} projects(s) updated")

    @staticmethod
    def get_project_info(manager: syncManager, item, source="todoist"):

        if source == "todoist":
            todoist_project_id = item["project_id"]
            project = manager.api.projects.get_by_id(todoist_project_id)['name']
            # if the project is not in notion, return none
            try:
                notion_project_id = projectManager.get_cross_bidict(manager)[todoist_project_id]
            except KeyError:
                notion_project_id = None

        else:
            if not item.project:
                project = []
                todoist_project_id = None
                notion_project_id = None
            else:
                project = item.project[0].title
                todoist_project_id = item.project[0].TodoistID
                notion_project_id = item.project[0].id

        return project, todoist_project_id, notion_project_id


class taskManager:

    @staticmethod
    def check_if_done(manager, row):
        # get dict of columns that contain labels
        label_config = manager.config['Label column name']

        for label_column in label_config.keys():
            labels = row.get_property(label_column)
            if not isinstance(labels, list):  # if column is single-select, convert it to a list
                labels = [labels]
            if set(labels).intersection(set(labelManager.get_done_labels(manager))):
                return True
        return False

    @staticmethod
    def compare_two_tasks(manager: syncManager, task1: task, task2: task):
        """task 1 takes priority over task 2 if there are differences,
           usually task1 is notion version and task2 is the todoist version."""

        task1_dict = task1.__dict__
        task2_dict = task2.__dict__

        new_task_dict = task1_dict.copy()
        updated_properties = []

        for (key, value1), value2 in zip(task1_dict.items(), task2_dict.values()):
            if value1 != value2 and key != "source":  # exclude the "source" item
                updated_properties.append(key)

                if value1 is None:
                    print(
                        f"{key}: {helper.strike(task1_dict['source'] + ': ' + str(value1))} -> "
                        f"{task2_dict['source'] + ': ' + str(value2)}")
                    new_task_dict[key] = value2
                else:
                    print(
                        f"{key}: {helper.strike(task2_dict['source'] + ': ' + str(value2))} -> "
                        f"{task1_dict['source'] + ': ' + str(value1)}")
                    new_task_dict[key] = value1
            else:
                new_task_dict[key] = value1

        new_task = task(source="merged",
                        task_id=new_task_dict["task_id"],
                        notion_task_id=new_task_dict["notion_task_id"],
                        content=new_task_dict["content"],
                        done=new_task_dict["done"],
                        due=new_task_dict["due"],
                        label_ids=new_task_dict["label_ids"],
                        label_names=new_task_dict["label_names"],
                        project_id=new_task_dict["project_id"],
                        notion_project_id=new_task_dict["notion_project_id"],
                        project_name=new_task_dict["project_name"],
                        todoist_note_id=new_task_dict["todoist_note_id"],
                        )

        return new_task, updated_properties

    @staticmethod
    def sync_notion_to_todoist(manager: syncManager):

        print("Syncing notion tasks to todoist...")
        new_project_count = 0
        updated_project_count = 0

        # sync todoist api
        manager.sync_todoist_api()

        # loop task by task
        # TODO: to eventually speed this up, we can filter by events changed within the last 24h, e.g.
        for row in manager.tasks.collection.get_rows():
            if not row.notionID:  # add the Notion ID to the row if it is not there already
                row.notionID = row.id

            notion_task = taskManager.from_notion(manager, row)  # get the task from Notion

            # check config for whether or not the event should be allowed to sync
            if not (not manager.config["Sync completed tasks"] and notion_task.done):
                if not row.todoistID:  # check if the task already has a notionID
                    new_item_id, new_note_id = taskManager.to_todoist(manager, notion_task)  # send to todoist
                    row.todoistID = new_item_id  # add the todoist item ID back to the row in Notion
                    print(f"Synced new Notion task {row.title} to Todoist.")
                    new_project_count += 1
                else:
                    # if it already has a todoistID, check for updates
                    todoist_item = manager.api.items.get_by_id(row.todoistID)
                    todoist_task = taskManager.from_todoist(manager, item=todoist_item)

                    # merge tasks and sync changes to both notion and todoist
                    new_task, updates = taskManager.compare_two_tasks(manager, notion_task, todoist_task)
                    taskManager.update_todoist_item(manager, new_task, updates)
                    taskManager.update_notion_item(manager, new_task, updates)

    @staticmethod
    def update_notion_item(manager: syncManager, item: task, updates: list):

        notion_item = manager.tasks.collection.get_rows(search=item.notion_task_id)[0]

        if "content" in updates:
            notion_item.title = item.content
        if "due" in updates:
            notion_item.due.start = NotionDate(datetime.datetime.strptime(item.due, "%Y-%m-%d").date())
        if "label_ids" in updates:

            # loop through each label column and add which labels apply
            for relevant_column, column_type in manager.config["Label column name"].items():

                if column_type == "select":
                    labels = ""
                else:
                    labels = []

                for label_id in item.label_ids:
                    label_row = manager.labels.collection.get_rows(search=str(label_id))[0]
                    label_column = label_row.relevant_column
                    label_name = label_row.notion_label
                    if label_column == relevant_column:
                        if column_type == "select":
                            labels = label_name
                        else:
                            labels.append(label_name)

                notion_item.set_property(relevant_column, labels)

        if "project" in updates:
            notion_item.move(project_id=item.project_id)
        if "done" in updates:
            if item.done:
                notion_item.complete()
            else:
                notion_item.uncomplete()

    @staticmethod
    def update_todoist_item(manager: syncManager, item: task, updates: list):

        todoist_item = manager.api.items.get_by_id(item.task_id)

        if "content" in updates:
            todoist_item.update(content=item.content)
        if "due" in updates:
            todoist_item.update(due=item.due)
        if "label_ids" in updates:
            todoist_item.update(labels=item.label_ids)
        if "project" in updates:
            todoist_item.move(project_id=item.project_id)
        if "done" in updates:
            if item.done:
                todoist_item.complete()
            else:
                todoist_item.uncomplete()

        manager.commit_todoist_api()

    @staticmethod
    def from_todoist(manager, item):

        is_done = True if item["checked"] == 1 else False

        # get project information
        project, todoist_project_id, notion_project_id = \
            projectManager.get_project_info(manager, item, source="todoist")

        # check if there is a notion task ID in notes:
        notion_id = None
        todoist_note_id = None
        for note in manager.api.notes.all():
            if note["item_id"] == item["id"] and "NotionID" in note["content"]:
                todoist_note_id = note["id"]
                notion_id = note["content"][10:]

        # check if due date data available
        try:
            due = item["due"]["date"]
        except TypeError:
            due = None

        new_task = task(
            source="todoist",
            task_id=item["id"],
            content=item["content"],
            done=is_done,
            due=due,
            label_ids=item["labels"],
            label_names=[manager.api.labels.get_by_id(label)['name'] for label in item['labels']],
            project_id=todoist_project_id,
            project_name=project,
            notion_task_id=notion_id,
            todoist_note_id=todoist_note_id,
            notion_project_id=notion_project_id,
        )

        return new_task

    @staticmethod
    def from_notion(manager, row):

        is_done = taskManager.check_if_done(manager, row)

        # get labels and projects
        todoist_labels, todoist_label_ids = labelManager.get_notion_labels(manager, row)
        project, todoist_project_id, notion_project_id = projectManager.get_project_info(manager, row, source="notion")

        # add notion ID to the task table
        row.NotionID = row.id

        new_task = task(
            source="notion",
            task_id=row.TodoistID,
            content=row.title,
            done=is_done,
            due=row.due.start.strftime(format="%Y-%m-%d"),
            label_ids=todoist_label_ids,
            label_names=todoist_labels,
            project_id=todoist_project_id,
            project_name=project,
            notion_task_id=row.id,
            notion_project_id=notion_project_id,

        )

        return new_task

    @staticmethod
    def to_notion(item: task, notion_table, project_table):

        notion_table.refresh()

        if not isinstance(item, task):
            raise TypeError("Input task must be of class `taskManager.task`.")

        if not isinstance(notion_table, notion.block.CollectionViewPageBlock):
            raise TypeError("Input table must be of `notion.block.CollectionViewPageBlock` type.")

        status = "Done 🙌" if item.done else \
            taskManager.label_translator(output="notion", todoist_id=item.label_ids[0])[1]

        project = project_table.collection.get_rows(search=str(item.project_id))[0]

        group = project.group[0]

        new_row = notion_table.collection.add_row()
        new_row.name = item.content
        new_row.TodoistID = item.task_id
        new_row.due = notion_table.collection.NotionDate(start=datetime.datetime.strptime(item.due, "%Y-%m-%d").date())
        new_row.status = status
        new_row.project = project
        new_row.NotionID = new_row.id
        new_row.group = group

        print(f"Imported task {item.content} with status {status}")

    @staticmethod
    def to_todoist(manager: syncManager, item: task):

        sync_message = manager.api.sync()

        manager.api.items.add(content=item.content,
                              due={"date": item.due},
                              labels=item.label_ids,
                              project_id=item.project_id,
                              )

        item_commit = manager.api.commit()
        new_item_id = item_commit['items'][0]['id']

        note = manager.api.notes.add(new_item_id, f"NotionID: {item.notion_task_id}")
        note_commit = manager.api.commit()
        new_note_id = note_commit['notes'][0]['id']

        return new_item_id, new_note_id

    @staticmethod
    def from_webhook(api, request_args):

        args = request_args

        is_done = True if args.get("checked") == 1 else False

        # check if there is a notion task ID in notes:
        notion_id = None
        for note in api.notes.all():
            if note["item_id"] == args.get('id') and "NotionID" in note["content"]:
                notion_note_id = note["id"]
                notion_id = note["content"][10:]

        # check if due data available
        try:
            due = args.get("due")["date"]
        except TypeError:
            due = None
        print("LABELS:")
        print([int(args.get('labels'))])
        print(api.labels.get_by_id(int(args.get('labels'))))
        print(api.labels.get_by_id(int(args.get('labels')))['name'])

        new_task = task(
            source="todoist",
            task_id=args.get('id'),
            content=args.get('content'),
            done=is_done,
            due=due,
            label_ids=[int(args.get('labels'))],
            label_names=[api.labels.get_by_id(label)['name'] for label in [int(args.get('labels'))]],
            project_id=args.get('project_id'),
            project_name=api.projects.get_by_id(int(args.get('project_id')))['name'],
            notion_project_id=notion_id
        )

        return new_task


class helper:

    @staticmethod
    def utc_to_local(utc_dt):
        return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)

    @staticmethod
    def strike(text):
        result = ''
        for c in str(text):
            result = result + c + '\u0336'
        return result
